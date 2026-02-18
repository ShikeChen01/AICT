"""
Pydantic schemas for project settings.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectSettingsResponse(BaseModel):
    """Response for GET/PATCH repositories/:id/settings."""

    id: UUID
    project_id: UUID
    max_engineers: int = 5
    persistent_sandbox_count: int = 1
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSettingsUpdate(BaseModel):
    """Request body for PATCH repositories/:id/settings."""

    max_engineers: int | None = Field(None, ge=0, le=20)
    persistent_sandbox_count: int | None = Field(None, ge=0, le=10)
