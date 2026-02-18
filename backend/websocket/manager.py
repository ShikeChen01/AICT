"""
WebSocket connection manager.

Docs contract (backend&API.md):
- agent_stream: agent_text, agent_tool_call, agent_tool_result
- messages: agent_message, system_message
- kanban: task_created, task_update
- agents: agent_status
- activity: agent_log, sandbox_log
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
    create_agent_log_event,
    create_agent_message_event,
    create_agent_status_event,
    create_agent_text_event,
    create_agent_tool_call_event,
    create_agent_tool_result_event,
    create_gm_status_event,
    create_sandbox_log_event,
    create_task_created_event,
    create_task_update_event,
    create_workflow_update_event,
)

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """WebSocket subscription channels (docs contract)."""
    AGENT_STREAM = "agent_stream"
    MESSAGES = "messages"
    KANBAN = "kanban"
    AGENTS = "agents"
    ACTIVITY = "activity"
    WORKFLOW = "workflow"
    ALL = "all"


class ConnectionInfo:
    """Stores information about a WebSocket connection."""

    def __init__(self, websocket: WebSocket, project_id: UUID):
        self.websocket = websocket
        self.project_id = project_id
        self.channels: set[Channel] = set()

    def subscribe(self, channel: Channel) -> None:
        self.channels.add(channel)
        if channel == Channel.ALL:
            self.channels.update([
                Channel.AGENT_STREAM,
                Channel.MESSAGES,
                Channel.KANBAN,
                Channel.AGENTS,
                Channel.ACTIVITY,
                Channel.WORKFLOW,
            ])

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

    async def broadcast_gm_status(self, project_id: UUID, status: str) -> int:
        """Broadcast GM/manager status change (agents channel)."""
        event = create_gm_status_event(project_id, status)
        return await self.broadcast(event, Channel.AGENTS, project_id)

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
        return await self.broadcast(event, Channel.AGENTS, agent.project_id)

    # ── Docs: agent stream & messages ─────────────────────────────

    async def broadcast_agent_text(
        self,
        project_id: UUID,
        agent_id: UUID,
        agent_role: str,
        content: str,
        session_id: UUID | None = None,
        iteration: int = 0,
    ) -> int:
        """Broadcast agent_text (incremental LLM output)."""
        event = create_agent_text_event(
            agent_id=agent_id,
            agent_role=agent_role,
            content=content,
            session_id=session_id,
            iteration=iteration,
        )
        return await self.broadcast(event, Channel.AGENT_STREAM, project_id)

    async def broadcast_agent_tool_call(
        self,
        project_id: UUID,
        agent_id: UUID,
        agent_role: str,
        tool_name: str,
        tool_input: dict,
        session_id: UUID | None = None,
        iteration: int = 0,
    ) -> int:
        """Broadcast agent_tool_call event."""
        event = create_agent_tool_call_event(
            agent_id=agent_id,
            agent_role=agent_role,
            tool_name=tool_name,
            tool_input=tool_input,
            session_id=session_id,
            iteration=iteration,
        )
        return await self.broadcast(event, Channel.AGENT_STREAM, project_id)

    async def broadcast_agent_tool_result(
        self,
        project_id: UUID,
        agent_id: UUID,
        tool_name: str,
        output: str,
        success: bool = True,
        session_id: UUID | None = None,
        iteration: int = 0,
    ) -> int:
        """Broadcast agent_tool_result event."""
        event = create_agent_tool_result_event(
            agent_id=agent_id,
            tool_name=tool_name,
            output=output,
            success=success,
            session_id=session_id,
            iteration=iteration,
        )
        return await self.broadcast(event, Channel.AGENT_STREAM, project_id)

    async def broadcast_agent_message(
        self,
        project_id: UUID,
        msg_id: UUID,
        from_agent_id: UUID,
        target_agent_id: UUID,
        content: str,
        message_type: str = "normal",
        created_at=None,
    ) -> int:
        """Broadcast agent_message (message to user)."""
        event = create_agent_message_event(
            msg_id=msg_id,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            content=content,
            message_type=message_type,
            created_at=created_at,
        )
        return await self.broadcast(event, Channel.MESSAGES, project_id)

    # ── Workflow & Activity broadcast methods (Frontend V2) ────────

    async def broadcast_workflow_update(
        self,
        project_id: UUID,
        thread_id: str,
        current_node: str,
        node_status: str,
        previous_node: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Broadcast workflow graph transition."""
        event = create_workflow_update_event(
            project_id=project_id,
            thread_id=thread_id,
            current_node=current_node,
            node_status=node_status,
            previous_node=previous_node,
            metadata=metadata,
        )
        return await self.broadcast(event, Channel.WORKFLOW, project_id)

    async def broadcast_agent_log(
        self,
        project_id: UUID,
        agent_id: UUID,
        agent_role: str,
        log_type: str,
        content: str,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: str | None = None,
    ) -> int:
        """Broadcast agent activity log (thought, tool use)."""
        event = create_agent_log_event(
            project_id=project_id,
            agent_id=agent_id,
            agent_role=agent_role,
            log_type=log_type,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_sandbox_log(
        self,
        project_id: UUID,
        agent_id: UUID,
        sandbox_id: str,
        stream: str,
        content: str,
    ) -> int:
        """Broadcast sandbox terminal output."""
        event = create_sandbox_log_event(
            project_id=project_id,
            agent_id=agent_id,
            sandbox_id=sandbox_id,
            stream=stream,
            content=content,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_to_project(
        self,
        project_id: UUID,
        data: dict,
    ) -> int:
        """
        Broadcast raw JSON data to all connections for a project.
        
        This is a low-level method for custom event types not covered
        by the typed event system.
        """
        async with self._lock:
            connections = list(self._connections.items())

        sent = 0
        failed_ids = []

        for conn_id, conn_info in connections:
            if conn_info.project_id != project_id:
                continue
            
            try:
                if conn_info.websocket.client_state == WebSocketState.CONNECTED:
                    await conn_info.websocket.send_json(data)
                    sent += 1
                else:
                    failed_ids.append(conn_id)
            except Exception as e:
                logger.warning(f"Failed to send to project {project_id}: {e}")
                failed_ids.append(conn_id)

        # Clean up failed connections
        if failed_ids:
            async with self._lock:
                for conn_id in failed_ids:
                    self._connections.pop(conn_id, None)

        return sent

    @property
    def active_connections(self) -> int:
        """Return count of active connections."""
        return len(self._connections)


# Singleton instance
ws_manager = WebSocketManager()
