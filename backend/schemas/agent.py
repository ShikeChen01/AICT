from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgentResponse(BaseModel):
    id: UUID
    project_id: UUID
    role: str
    display_name: str
    model: str
    status: str
    current_task_id: UUID | None
    sandbox_id: str | None
    sandbox_persist: bool
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
