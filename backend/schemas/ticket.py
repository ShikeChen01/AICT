from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    to_agent_id: UUID
    header: str
    ticket_type: str  # 'task_assignment', 'question', 'help', 'issue'
    critical: int = Field(default=5, ge=0, le=10)
    urgent: int = Field(default=5, ge=0, le=10)
    initial_message: str | None = None


class TicketMessageCreate(BaseModel):
    content: str


class TicketMessageResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    from_agent_id: UUID | None = None
    from_user_id: UUID | None = None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketResponse(BaseModel):
    id: UUID
    project_id: UUID
    from_agent_id: UUID
    to_agent_id: UUID
    header: str
    ticket_type: str
    critical: int
    urgent: int
    status: str
    created_at: datetime
    closed_at: datetime | None
    closed_by_id: UUID | None
    messages: list[TicketMessageResponse] = []

    model_config = {"from_attributes": True}
