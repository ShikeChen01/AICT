"""
WebSocket connection manager.

Handles:
- Connection lifecycle
- Channel subscriptions (chat, kanban)
- Broadcasting events to subscribers
"""

import asyncio
import logging
from enum import Enum
from uuid import UUID

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from backend.websocket.events import (
    EventType,
    WebSocketEvent,
    create_agent_status_event,
    create_chat_message_event,
    create_gm_status_event,
    create_task_created_event,
    create_task_update_event,
)

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """WebSocket subscription channels."""
    CHAT = "chat"
    KANBAN = "kanban"
    ALL = "all"  # Subscribe to everything


class ConnectionInfo:
    """Stores information about a WebSocket connection."""

    def __init__(self, websocket: WebSocket, project_id: UUID):
        self.websocket = websocket
        self.project_id = project_id
        self.channels: set[Channel] = set()

    def subscribe(self, channel: Channel) -> None:
        self.channels.add(channel)
        if channel == Channel.ALL:
            self.channels.update([Channel.CHAT, Channel.KANBAN])

    def unsubscribe(self, channel: Channel) -> None:
        self.channels.discard(channel)

    def is_subscribed(self, channel: Channel) -> bool:
        return channel in self.channels or Channel.ALL in self.channels


class WebSocketManager:
    """
    Manages WebSocket connections and message broadcasting.

    Thread-safe singleton that handles multiple concurrent connections.
    """

    def __init__(self):
        # connection_id -> ConnectionInfo
        self._connections: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()

    def _connection_id(self, websocket: WebSocket) -> str:
        """Generate unique connection ID."""
        return f"{id(websocket)}"

    async def connect(
        self,
        websocket: WebSocket,
        project_id: UUID,
        channels: list[Channel] | None = None,
    ) -> str:
        """
        Accept a WebSocket connection and register it.

        Returns connection ID.
        """
        await websocket.accept()

        conn_id = self._connection_id(websocket)
        conn_info = ConnectionInfo(websocket, project_id)

        # Subscribe to requested channels (default: all)
        if channels:
            for ch in channels:
                conn_info.subscribe(ch)
        else:
            conn_info.subscribe(Channel.ALL)

        async with self._lock:
            self._connections[conn_id] = conn_info

        logger.info(f"WebSocket connected: {conn_id}, project: {project_id}")
        return conn_id

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        conn_id = self._connection_id(websocket)

        async with self._lock:
            if conn_id in self._connections:
                del self._connections[conn_id]
                logger.info(f"WebSocket disconnected: {conn_id}")

    async def subscribe(self, websocket: WebSocket, channel: Channel) -> None:
        """Subscribe a connection to a channel."""
        conn_id = self._connection_id(websocket)

        async with self._lock:
            if conn_id in self._connections:
                self._connections[conn_id].subscribe(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: Channel) -> None:
        """Unsubscribe a connection from a channel."""
        conn_id = self._connection_id(websocket)

        async with self._lock:
            if conn_id in self._connections:
                self._connections[conn_id].unsubscribe(channel)

    async def _send_event(self, conn_info: ConnectionInfo, event: WebSocketEvent) -> bool:
        """
        Send event to a single connection.
        Returns True if successful, False if connection should be removed.
        """
        try:
            if conn_info.websocket.client_state == WebSocketState.CONNECTED:
                await conn_info.websocket.send_json(event.model_dump(mode="json"))
                return True
        except Exception as e:
            logger.warning(f"Failed to send event: {e}")
        return False

    async def broadcast(
        self,
        event: WebSocketEvent,
        channel: Channel,
        project_id: UUID | None = None,
    ) -> int:
        """
        Broadcast an event to all subscribers of a channel.

        If project_id is provided, only sends to connections for that project.
        Returns number of successful sends.
        """
        async with self._lock:
            connections = list(self._connections.items())

        sent = 0
        failed_ids = []

        for conn_id, conn_info in connections:
            # Filter by project if specified
            if project_id and conn_info.project_id != project_id:
                continue

            # Check channel subscription
            if not conn_info.is_subscribed(channel):
                continue

            if await self._send_event(conn_info, event):
                sent += 1
            else:
                failed_ids.append(conn_id)

        # Clean up failed connections
        if failed_ids:
            async with self._lock:
                for conn_id in failed_ids:
                    self._connections.pop(conn_id, None)

        return sent

    # ── Convenience broadcast methods ─────────────────────────────

    async def broadcast_chat_message(self, message) -> int:
        """Broadcast a chat message event."""
        event = create_chat_message_event(message)
        return await self.broadcast(event, Channel.CHAT, message.project_id)

    async def broadcast_gm_status(self, project_id: UUID, status: str) -> int:
        """Broadcast GM status change."""
        event = create_gm_status_event(project_id, status)
        return await self.broadcast(event, Channel.CHAT, project_id)

    async def broadcast_task_created(self, task) -> int:
        """Broadcast task created event."""
        event = create_task_created_event(task)
        return await self.broadcast(event, Channel.KANBAN, task.project_id)

    async def broadcast_task_update(self, task) -> int:
        """Broadcast task update event."""
        event = create_task_update_event(task)
        return await self.broadcast(event, Channel.KANBAN, task.project_id)

    async def broadcast_agent_status(self, agent) -> int:
        """Broadcast agent status change."""
        event = create_agent_status_event(agent)
        return await self.broadcast(event, Channel.KANBAN, agent.project_id)

    @property
    def active_connections(self) -> int:
        """Return count of active connections."""
        return len(self._connections)


# Singleton instance
ws_manager = WebSocketManager()
