from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    code_repo_url: str


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code_repo_url: str | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    spec_repo_path: str
    code_repo_url: str
    code_repo_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
