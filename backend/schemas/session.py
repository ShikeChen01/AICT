"""
Pydantic schemas for agent sessions and session messages.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgentSessionResponse(BaseModel):
    """Response for GET sessions (list/detail)."""

    id: UUID
    agent_id: UUID
    project_id: UUID
    task_id: UUID | None
    trigger_message_id: UUID | None
    status: str
    end_reason: str | None
    iteration_count: int
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class AgentMessageResponse(BaseModel):
    """Response for GET sessions/:id/messages."""

    id: UUID
    agent_id: UUID
    session_id: UUID | None
    project_id: UUID
    role: str
    content: str
    tool_name: str | None
    tool_input: dict | None
    loop_iteration: int
    created_at: datetime

    model_config = {"from_attributes": True}
