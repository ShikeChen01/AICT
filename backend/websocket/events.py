"""
WebSocket event types and payload definitions.

Docs contract (backend&API.md):
- agent_stream: agent_text, agent_tool_call, agent_tool_result
- messages: agent_message, system_message
- kanban: task_created, task_update
- agents: agent_status
- activity: agent_log, sandbox_log
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EventType(str, Enum):
    # Agent stream (docs)
    AGENT_TEXT = "agent_text"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_TOOL_RESULT = "agent_tool_result"

    # Messages (docs)
    AGENT_MESSAGE = "agent_message"
    SYSTEM_MESSAGE = "system_message"

    # Kanban
    TASK_CREATED = "task_created"
    TASK_UPDATE = "task_update"
    AGENT_STATUS = "agent_status"

    # Workflow / activity
    WORKFLOW_UPDATE = "workflow_update"
    AGENT_LOG = "agent_log"
    SANDBOX_LOG = "sandbox_log"
    BACKEND_LOG = "backend_log"
    BACKEND_LOG_SNAPSHOT = "backend_log_snapshot"

    # LLM usage (real-time cost/token stream)
    USAGE_UPDATE = "usage_update"

    # Agent lifecycle
    AGENT_STOPPED = "agent_stopped"


class WebSocketEvent(BaseModel):
    """Base WebSocket event structure."""
    type: EventType
    data: dict[str, Any]
    timestamp: datetime = None

    def __init__(self, **kwargs):
        if kwargs.get("timestamp") is None:
            kwargs["timestamp"] = datetime.now()
        super().__init__(**kwargs)


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


class BackendLogItemPayload(BaseModel):
    """Payload for one backend application log entry."""
    seq: int
    ts: str
    level: str
    logger: str
    message: str


class BackendLogSnapshotPayload(BaseModel):
    """Payload containing buffered backend logs for initial websocket sync."""
    items: list[BackendLogItemPayload]
    latest_seq: int = 0


# ── Agent stream payloads (docs) ───────────────────────────────────


class AgentTextPayload(BaseModel):
    """Incremental text chunk from agent loop."""
    agent_id: UUID
    agent_role: str
    content: str
    session_id: UUID | None = None
    iteration: int = 0


class AgentToolCallPayload(BaseModel):
    """Tool call initiated by agent."""
    agent_id: UUID
    agent_role: str
    tool_name: str
    tool_input: dict[str, Any]
    session_id: UUID | None = None
    iteration: int = 0


class AgentToolResultPayload(BaseModel):
    """Tool result (truncated if large)."""
    agent_id: UUID
    agent_role: str | None = None
    tool_name: str
    output: str
    success: bool = True
    session_id: UUID | None = None
    iteration: int = 0


class AgentMessagePayload(BaseModel):
    """Message to user (target_agent_id = USER_AGENT_ID)."""
    id: UUID
    from_agent_id: UUID
    target_agent_id: UUID
    content: str
    message_type: str = "normal"
    created_at: datetime | None = None


# ── Event Factory Functions ────────────────────────────────────────


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


def create_backend_log_event(
    seq: int,
    ts: str,
    level: str,
    logger: str,
    message: str,
) -> WebSocketEvent:
    """Create incremental backend_log event."""
    return WebSocketEvent(
        type=EventType.BACKEND_LOG,
        data=BackendLogItemPayload(
            seq=seq,
            ts=ts,
            level=level,
            logger=logger,
            message=message,
        ).model_dump(mode="json"),
    )


def create_backend_log_snapshot_event(
    items: list[dict[str, Any]],
    latest_seq: int,
) -> WebSocketEvent:
    """Create backend_log_snapshot event with buffered items."""
    payload_items = [BackendLogItemPayload(**item) for item in items]
    return WebSocketEvent(
        type=EventType.BACKEND_LOG_SNAPSHOT,
        data=BackendLogSnapshotPayload(
            items=payload_items,
            latest_seq=latest_seq,
        ).model_dump(mode="json"),
    )


# ── Agent stream / message factories (docs) ────────────────────────


def create_agent_text_event(
    agent_id: UUID,
    agent_role: str,
    content: str,
    session_id: UUID | None = None,
    iteration: int = 0,
) -> WebSocketEvent:
    """Create agent_text event (incremental LLM output)."""
    return WebSocketEvent(
        type=EventType.AGENT_TEXT,
        data=AgentTextPayload(
            agent_id=agent_id,
            agent_role=agent_role,
            content=content,
            session_id=session_id,
            iteration=iteration,
        ).model_dump(mode="json"),
    )


def create_agent_tool_call_event(
    agent_id: UUID,
    agent_role: str,
    tool_name: str,
    tool_input: dict[str, Any],
    session_id: UUID | None = None,
    iteration: int = 0,
) -> WebSocketEvent:
    """Create agent_tool_call event."""
    return WebSocketEvent(
        type=EventType.AGENT_TOOL_CALL,
        data=AgentToolCallPayload(
            agent_id=agent_id,
            agent_role=agent_role,
            tool_name=tool_name,
            tool_input=tool_input,
            session_id=session_id,
            iteration=iteration,
        ).model_dump(mode="json"),
    )


def create_agent_tool_result_event(
    agent_id: UUID,
    tool_name: str,
    output: str,
    success: bool = True,
    session_id: UUID | None = None,
    iteration: int = 0,
    agent_role: str | None = None,
) -> WebSocketEvent:
    """Create agent_tool_result event."""
    return WebSocketEvent(
        type=EventType.AGENT_TOOL_RESULT,
        data=AgentToolResultPayload(
            agent_id=agent_id,
            agent_role=agent_role,
            tool_name=tool_name,
            output=output,
            success=success,
            session_id=session_id,
            iteration=iteration,
        ).model_dump(mode="json"),
    )


def create_agent_message_event(
    msg_id: UUID,
    from_agent_id: UUID,
    target_agent_id: UUID,
    content: str,
    message_type: str = "normal",
    created_at: datetime | None = None,
) -> WebSocketEvent:
    """Create agent_message event (message to user)."""
    return WebSocketEvent(
        type=EventType.AGENT_MESSAGE,
        data=AgentMessagePayload(
            id=msg_id,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            content=content,
            message_type=message_type,
            created_at=created_at,
        ).model_dump(mode="json"),
    )


# ── Usage update payload ───────────────────────────────────────────


class UsageUpdatePayload(BaseModel):
    """One LLM call recorded — sent after every successful agent LLM call."""
    project_id: UUID
    agent_id: UUID | None
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    created_at: str


def create_usage_update_event(
    *,
    project_id: UUID,
    agent_id: UUID | None,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
    created_at: str,
) -> WebSocketEvent:
    """Create usage_update event emitted after each LLM call."""
    return WebSocketEvent(
        type=EventType.USAGE_UPDATE,
        data=UsageUpdatePayload(
            project_id=project_id,
            agent_id=agent_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            created_at=created_at,
        ).model_dump(mode="json"),
    )
