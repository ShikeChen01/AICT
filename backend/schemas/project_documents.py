"""Pydantic schemas for project_documents (read-only for users)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    doc_type: str
    title: str | None
    content: str | None
    updated_by_agent_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectDocumentSummaryResponse(BaseModel):
    """List-view response — content omitted to keep payloads small."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    doc_type: str
    title: str | None
    updated_by_agent_id: UUID | None
    updated_at: datetime
