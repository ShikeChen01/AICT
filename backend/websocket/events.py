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

    # Workflow events (Frontend V2)
    WORKFLOW_UPDATE = "workflow_update"
    AGENT_LOG = "agent_log"
    SANDBOX_LOG = "sandbox_log"

    # Engineer job events
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"

    # Ticket events
    TICKET_CREATED = "ticket_created"
    TICKET_REPLY = "ticket_reply"
    TICKET_CLOSED = "ticket_closed"
    MISSION_ABORTED = "mission_aborted"


class WebSocketEvent(BaseModel):
    """Base WebSocket event structure."""
    type: EventType
    data: dict[str, Any]
    timestamp: datetime = None

    def __init__(self, **kwargs):
        if kwargs.get("timestamp") is None:
            kwargs["timestamp"] = datetime.now()
        super().__init__(**kwargs)


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


# ── Workflow Events (Frontend V2) ─────────────────────────────────


class WorkflowUpdatePayload(BaseModel):
    """Payload for workflow node transitions."""
    project_id: UUID
    thread_id: str  # LangGraph thread_id
    previous_node: str | None
    current_node: str
    node_status: str  # 'started', 'completed', 'error'
    metadata: dict[str, Any] | None = None


class AgentLogPayload(BaseModel):
    """Payload for agent activity logs (internal thought, tool use)."""
    project_id: UUID
    agent_id: UUID
    agent_role: str
    log_type: str  # 'thought', 'tool_call', 'tool_result', 'message'
    content: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None


class SandboxLogPayload(BaseModel):
    """Payload for E2B sandbox output (terminal logs)."""
    project_id: UUID
    agent_id: UUID
    sandbox_id: str
    stream: str  # 'stdout', 'stderr'
    content: str


# ── Engineer Job Events ───────────────────────────────────────────


class JobEventPayload(BaseModel):
    """Payload for engineer job status events."""
    job_id: UUID
    project_id: UUID
    task_id: UUID
    agent_id: UUID
    status: str  # started, progress, completed, failed
    message: str | None = None
    result: str | None = None
    error: str | None = None
    pr_url: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None


class TicketEventPayload(BaseModel):
    """Payload for ticket events."""
    ticket_id: UUID
    project_id: UUID
    from_agent_id: UUID | None = None
    from_user_id: UUID | None = None
    to_agent_id: UUID
    header: str
    ticket_type: str
    message: str | None = None


# ── Event Factory Functions ────────────────────────────────────────


def create_chat_message_event(message) -> WebSocketEvent:
    """Create a chat message WebSocket event."""
    return WebSocketEvent(
        type=EventType.CHAT_MESSAGE,
        data=ChatMessagePayload(
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
        data=GMStatusPayload(
            project_id=project_id,
            status=status,
        ).model_dump(mode="json"),
    )


def create_task_created_event(task) -> WebSocketEvent:
    """Create a task created WebSocket event."""
    return WebSocketEvent(
        type=EventType.TASK_CREATED,
        data=TaskPayload(
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
        data=TaskPayload(
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
        data=AgentStatusPayload(
            id=agent.id,
            project_id=agent.project_id,
            role=agent.role,
            display_name=agent.display_name,
            status=agent.status,
            current_task_id=agent.current_task_id,
        ).model_dump(mode="json"),
    )


# ── Workflow Event Factories (Frontend V2) ─────────────────────────


def create_workflow_update_event(
    project_id: UUID,
    thread_id: str,
    current_node: str,
    node_status: str,
    previous_node: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebSocketEvent:
    """Create a workflow update event for graph transitions."""
    return WebSocketEvent(
        type=EventType.WORKFLOW_UPDATE,
        data=WorkflowUpdatePayload(
            project_id=project_id,
            thread_id=thread_id,
            previous_node=previous_node,
            current_node=current_node,
            node_status=node_status,
            metadata=metadata,
        ).model_dump(mode="json"),
    )


def create_agent_log_event(
    project_id: UUID,
    agent_id: UUID,
    agent_role: str,
    log_type: str,
    content: str,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
    tool_output: str | None = None,
) -> WebSocketEvent:
    """Create an agent log event for activity feed."""
    return WebSocketEvent(
        type=EventType.AGENT_LOG,
        data=AgentLogPayload(
            project_id=project_id,
            agent_id=agent_id,
            agent_role=agent_role,
            log_type=log_type,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        ).model_dump(mode="json"),
    )


def create_sandbox_log_event(
    project_id: UUID,
    agent_id: UUID,
    sandbox_id: str,
    stream: str,
    content: str,
) -> WebSocketEvent:
    """Create a sandbox log event for terminal output."""
    return WebSocketEvent(
        type=EventType.SANDBOX_LOG,
        data=SandboxLogPayload(
            project_id=project_id,
            agent_id=agent_id,
            sandbox_id=sandbox_id,
            stream=stream,
            content=content,
        ).model_dump(mode="json"),
    )


# ── Job Event Factories ────────────────────────────────────────────


def create_job_started_event(
    job_id: UUID,
    project_id: UUID,
    task_id: UUID,
    agent_id: UUID,
    message: str | None = None,
) -> WebSocketEvent:
    """Create a job started event."""
    return WebSocketEvent(
        type=EventType.JOB_STARTED,
        data=JobEventPayload(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            status="started",
            message=message,
        ).model_dump(mode="json"),
    )


def create_job_progress_event(
    job_id: UUID,
    project_id: UUID,
    task_id: UUID,
    agent_id: UUID,
    message: str | None = None,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
) -> WebSocketEvent:
    """Create a job progress event."""
    return WebSocketEvent(
        type=EventType.JOB_PROGRESS,
        data=JobEventPayload(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            status="progress",
            message=message,
            tool_name=tool_name,
            tool_args=tool_args,
        ).model_dump(mode="json"),
    )


def create_job_completed_event(
    job_id: UUID,
    project_id: UUID,
    task_id: UUID,
    agent_id: UUID,
    result: str | None = None,
    pr_url: str | None = None,
) -> WebSocketEvent:
    """Create a job completed event."""
    return WebSocketEvent(
        type=EventType.JOB_COMPLETED,
        data=JobEventPayload(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            status="completed",
            result=result,
            pr_url=pr_url,
        ).model_dump(mode="json"),
    )


def create_job_failed_event(
    job_id: UUID,
    project_id: UUID,
    task_id: UUID,
    agent_id: UUID,
    error: str,
) -> WebSocketEvent:
    """Create a job failed event."""
    return WebSocketEvent(
        type=EventType.JOB_FAILED,
        data=JobEventPayload(
            job_id=job_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            status="failed",
            error=error,
        ).model_dump(mode="json"),
    )


# ── Ticket Event Factories ─────────────────────────────────────────


def create_ticket_created_event(
    ticket_id: UUID,
    project_id: UUID,
    from_agent_id: UUID,
    to_agent_id: UUID,
    header: str,
    ticket_type: str,
    message: str | None = None,
) -> WebSocketEvent:
    """Create a ticket created event."""
    return WebSocketEvent(
        type=EventType.TICKET_CREATED,
        data=TicketEventPayload(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            from_user_id=None,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
            message=message,
        ).model_dump(mode="json"),
    )


def create_ticket_reply_event(
    ticket_id: UUID,
    project_id: UUID,
    to_agent_id: UUID,
    header: str,
    ticket_type: str,
    message: str | None = None,
    from_agent_id: UUID | None = None,
    from_user_id: UUID | None = None,
) -> WebSocketEvent:
    """Create a ticket reply event."""
    return WebSocketEvent(
        type=EventType.TICKET_REPLY,
        data=TicketEventPayload(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            from_user_id=from_user_id,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
            message=message,
        ).model_dump(mode="json"),
    )


def create_ticket_closed_event(
    ticket_id: UUID,
    project_id: UUID,
    from_agent_id: UUID | None,
    to_agent_id: UUID,
    header: str,
    ticket_type: str,
) -> WebSocketEvent:
    """Create a ticket closed event."""
    return WebSocketEvent(
        type=EventType.TICKET_CLOSED,
        data=TicketEventPayload(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            from_user_id=None,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type=ticket_type,
            message=None,
        ).model_dump(mode="json"),
    )


def create_mission_aborted_event(
    ticket_id: UUID,
    project_id: UUID,
    from_agent_id: UUID,
    to_agent_id: UUID,
    header: str,
    message: str | None = None,
) -> WebSocketEvent:
    """Create a mission aborted event."""
    return WebSocketEvent(
        type=EventType.MISSION_ABORTED,
        data=TicketEventPayload(
            ticket_id=ticket_id,
            project_id=project_id,
            from_agent_id=from_agent_id,
            from_user_id=None,
            to_agent_id=to_agent_id,
            header=header,
            ticket_type="abort",
            message=message,
        ).model_dump(mode="json"),
    )
