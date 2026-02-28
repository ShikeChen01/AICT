"""Pydantic schemas for file attachments (Phase 6)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    """Metadata returned after upload or on metadata fetch (no binary data)."""

    id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID | None
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime

    model_config = {"from_attributes": True}
