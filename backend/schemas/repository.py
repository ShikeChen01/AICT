from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RepositoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    code_repo_url: str | None = Field(None, description="Optional Git URL to clone; if omitted, project is created without a linked repo.")


class RepositoryImport(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    code_repo_url: str = Field(..., min_length=1, description="Git URL to clone")


class RepositoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code_repo_url: str | None = None


class RepositoryResponse(BaseModel):
    id: UUID
    owner_id: UUID | None = None
    name: str
    description: str | None
    spec_repo_path: str
    code_repo_url: str
    code_repo_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
