"""
Pydantic schemas for project settings.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectSettingsResponse(BaseModel):
    """Response for GET/PATCH repositories/:id/settings."""

    id: UUID
    project_id: UUID
    max_engineers: int = 5
    persistent_sandbox_count: int = 1
    # Phase 3: per-project model and prompt overrides
    model_overrides: dict[str, Any] | None = None
    prompt_overrides: dict[str, Any] | None = None
    # Phase 4: daily token budget (0 = unlimited)
    daily_token_budget: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSettingsUpdate(BaseModel):
    """Request body for PATCH repositories/:id/settings."""

    max_engineers: int | None = Field(None, ge=0, le=20)
    persistent_sandbox_count: int | None = Field(None, ge=0, le=10)
    # Phase 3: pass None to leave unchanged, pass {} to clear all overrides
    model_overrides: dict[str, Any] | None = None
    prompt_overrides: dict[str, Any] | None = None
    # Phase 4: 0 = unlimited, >0 = max tokens/day
    daily_token_budget: int | None = Field(None, ge=0)
