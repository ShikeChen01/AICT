from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    status: str = "backlog"
    critical: int = Field(default=5, ge=0, le=10)
    urgent: int = Field(default=5, ge=0, le=10)
    module_path: str | None = None
    parent_task_id: UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    critical: int | None = Field(default=None, ge=0, le=10)
    urgent: int | None = Field(default=None, ge=0, le=10)
    assigned_agent_id: UUID | None = None
    module_path: str | None = None
    git_branch: str | None = None
    pr_url: str | None = None


class TaskResponse(BaseModel):
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

    model_config = {"from_attributes": True}
