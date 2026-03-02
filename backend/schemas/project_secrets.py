"""
Pydantic schemas for project secrets (per-project tokens for agent use).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectSecretResponse(BaseModel):
    """Response for GET repositories/:id/secrets — never includes plaintext value."""

    id: UUID
    name: str
    hint: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectSecretUpsert(BaseModel):
    """Request body for POST repositories/:id/secrets (create or update by name)."""

    name: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)
