"""
WebSocket event types and payload definitions.

Events:
- chat_message: GM responds to user
- gm_status: GM busy/available
- task_created: New task created
- task_update: Task status/assignment changed
- agent_status: Agent sleeping/active/busy
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EventType(str, Enum):
    # Chat events
    CHAT_MESSAGE = "chat_message"
    GM_STATUS = "gm_status"

    # Kanban events
    TASK_CREATED = "task_created"
    TASK_UPDATE = "task_update"

    # Agent events
    AGENT_STATUS = "agent_status"


class WebSocketEvent(BaseModel):
    """Base WebSocket event structure."""
    type: EventType
    payload: dict[str, Any]
    timestamp: datetime = None

    def __init__(self, **data):
        if data.get("timestamp") is None:
            data["timestamp"] = datetime.now()
        super().__init__(**data)


# ── Chat Events ────────────────────────────────────────────────────


class ChatMessagePayload(BaseModel):
    id: UUID
    project_id: UUID
    role: str  # 'user' or 'gm'
    content: str
    attachments: list | None = None
    created_at: datetime


class GMStatusPayload(BaseModel):
    project_id: UUID
    status: str  # 'busy' or 'available'


# ── Task Events ────────────────────────────────────────────────────


class TaskPayload(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    description: str | None
    status: str
    critical: int
    urgent: int
    assigned_agent_id: UUID | None
    module_path: str | None
    git_branch: str | None
    pr_url: str | None
    parent_task_id: UUID | None
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


# ── Agent Events ───────────────────────────────────────────────────


class AgentStatusPayload(BaseModel):
    id: UUID
    project_id: UUID
    role: str
    display_name: str
    status: str  # 'sleeping', 'active', 'busy'
    current_task_id: UUID | None


# ── Event Factory Functions ────────────────────────────────────────


def create_chat_message_event(message) -> WebSocketEvent:
    """Create a chat message WebSocket event."""
    return WebSocketEvent(
        type=EventType.CHAT_MESSAGE,
        payload=ChatMessagePayload(
            id=message.id,
            project_id=message.project_id,
            role=message.role,
            content=message.content,
            attachments=message.attachments,
            created_at=message.created_at,
        ).model_dump(mode="json"),
    )


def create_gm_status_event(project_id: UUID, status: str) -> WebSocketEvent:
    """Create a GM status WebSocket event."""
    return WebSocketEvent(
        type=EventType.GM_STATUS,
        payload=GMStatusPayload(
            project_id=project_id,
            status=status,
        ).model_dump(mode="json"),
    )


def create_task_created_event(task) -> WebSocketEvent:
    """Create a task created WebSocket event."""
    return WebSocketEvent(
        type=EventType.TASK_CREATED,
        payload=TaskPayload(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status,
            critical=task.critical,
            urgent=task.urgent,
            assigned_agent_id=task.assigned_agent_id,
            module_path=task.module_path,
            git_branch=task.git_branch,
            pr_url=task.pr_url,
            parent_task_id=task.parent_task_id,
            created_by_id=task.created_by_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        ).model_dump(mode="json"),
    )


def create_task_update_event(task) -> WebSocketEvent:
    """Create a task update WebSocket event."""
    return WebSocketEvent(
        type=EventType.TASK_UPDATE,
        payload=TaskPayload(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status,
            critical=task.critical,
            urgent=task.urgent,
            assigned_agent_id=task.assigned_agent_id,
            module_path=task.module_path,
            git_branch=task.git_branch,
            pr_url=task.pr_url,
            parent_task_id=task.parent_task_id,
            created_by_id=task.created_by_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        ).model_dump(mode="json"),
    )


def create_agent_status_event(agent) -> WebSocketEvent:
    """Create an agent status WebSocket event."""
    return WebSocketEvent(
        type=EventType.AGENT_STATUS,
        payload=AgentStatusPayload(
            id=agent.id,
            project_id=agent.project_id,
            role=agent.role,
            display_name=agent.display_name,
            status=agent.status,
            current_task_id=agent.current_task_id,
        ).model_dump(mode="json"),
    )
