from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    content: str
    attachments: list | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    project_id: UUID
    role: str
    content: str
    attachments: list | None
    created_at: datetime

    model_config = {"from_attributes": True}
