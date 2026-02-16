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
    create_agent_log_event,
    create_agent_status_event,
    create_chat_message_event,
    create_gm_status_event,
    create_job_completed_event,
    create_job_failed_event,
    create_job_progress_event,
    create_job_started_event,
    create_mission_aborted_event,
    create_sandbox_log_event,
    create_task_created_event,
    create_ticket_closed_event,
    create_ticket_created_event,
    create_ticket_reply_event,
    create_task_update_event,
    create_workflow_update_event,
)

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """WebSocket subscription channels."""
    CHAT = "chat"
    KANBAN = "kanban"
    WORKFLOW = "workflow"  # Frontend V2: workflow graph updates
    ACTIVITY = "activity"  # Frontend V2: agent activity feed
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
            self.channels.update([Channel.CHAT, Channel.KANBAN, Channel.WORKFLOW, Channel.ACTIVITY])

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

    # ── Job broadcast methods ──────────────────────────────────────

    async def broadcast_job_started(
        self,
        job_id: UUID,
        project_id: UUID,
        task_id: UUID,
        agent_id: UUID,
        message: str | None = None,
    ) -> int:
        """Broadcast job started event."""
        event = create_job_started_event(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            message=message,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_job_progress(
        self,
        job_id: UUID,
        project_id: UUID,
        task_id: UUID,
        agent_id: UUID,
        message: str | None = None,
        tool_name: str | None = None,
        tool_args: dict | None = None,
    ) -> int:
        """Broadcast job progress event."""
        event = create_job_progress_event(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            message=message,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_job_completed(
        self,
        job_id: UUID,
        project_id: UUID,
        task_id: UUID,
        agent_id: UUID,
        result: str | None = None,
        pr_url: str | None = None,
    ) -> int:
        """Broadcast job completed event."""
        event = create_job_completed_event(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            result=result,
            pr_url=pr_url,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_job_failed(
        self,
        job_id: UUID,
        project_id: UUID,
        task_id: UUID,
        agent_id: UUID,
        error: str,
    ) -> int:
        """Broadcast job failed event."""
        event = create_job_failed_event(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            error=error,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    # ── Ticket broadcast methods ─────────────────────────────────────

    async def broadcast_ticket_created(
        self,
        ticket_id: UUID,
        project_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        header: str,
        ticket_type: str,
        message: str | None = None,
    ) -> int:
        """Broadcast ticket created event."""
        event = create_ticket_created_event(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
            message=message,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_ticket_reply(
        self,
        ticket_id: UUID,
        project_id: UUID,
        to_agent_id: UUID,
        header: str,
        ticket_type: str,
        message: str | None = None,
        from_agent_id: UUID | None = None,
        from_user_id: UUID | None = None,
    ) -> int:
        """Broadcast ticket reply event."""
        event = create_ticket_reply_event(
            ticket_id=ticket_id,
            project_id=project_id,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
            message=message,
            from_agent_id=from_agent_id,
            from_user_id=from_user_id,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_ticket_closed(
        self,
        ticket_id: UUID,
        project_id: UUID,
        from_agent_id: UUID | None,
        to_agent_id: UUID,
        header: str,
        ticket_type: str,
    ) -> int:
        """Broadcast ticket closed event."""
        event = create_ticket_closed_event(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    async def broadcast_mission_aborted(
        self,
        ticket_id: UUID,
        project_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        header: str,
        message: str | None = None,
    ) -> int:
        """Broadcast mission aborted event."""
        event = create_mission_aborted_event(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            header=header,
            message=message,
        )
        return await self.broadcast(event, Channel.ACTIVITY, project_id)

    @property
    def active_connections(self) -> int:
        """Return count of active connections."""
        return len(self._connections)


# Singleton instance
ws_manager = WebSocketManager()
