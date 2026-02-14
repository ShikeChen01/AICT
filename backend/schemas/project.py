from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Create a new blank project."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    code_repo_url: str = Field(default="", description="Git URL (optional for blank projects)")


class ProjectImport(BaseModel):
    """Import an existing Git repository as a new project."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    code_repo_url: str = Field(..., min_length=1, description="Git URL to clone")
    git_token: str | None = Field(default=None, description="Personal Access Token for private repos")


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code_repo_url: str | None = None
    git_token: str | None = Field(default=None, description="Update stored PAT")


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    spec_repo_path: str
    code_repo_url: str
    code_repo_path: str
    git_token_set: bool = Field(default=False, description="Whether a Git token is configured")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
