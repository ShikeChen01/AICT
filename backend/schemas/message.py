"""
Pydantic schemas for channel messages (user-to-agent messaging).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelMessageSend(BaseModel):
    """Request body for POST /messages/send."""

    project_id: UUID
    target_agent_id: UUID = Field(..., description="Agent to send the message to")
    content: str = Field(..., min_length=1)


class ChannelMessageResponse(BaseModel):
    """Response for channel message (send, list)."""

    id: UUID
    project_id: UUID
    from_agent_id: UUID | None
    target_agent_id: UUID | None
    content: str
    message_type: str  # 'normal' | 'system'
    status: str  # 'sent' | 'received' | 'read'
    broadcast: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# Internal API (tools): notify_user, broadcast_message request bodies
class InternalSendMessage(BaseModel):
    """Internal: send message from agent to target."""

    from_agent_id: UUID
    target_agent_id: UUID | None  # None for broadcast
    project_id: UUID
    content: str = Field(..., min_length=1)
    message_type: str = "normal"  # 'normal' | 'system'


class InternalBroadcastMessage(BaseModel):
    """Internal: broadcast message (write only, no wake)."""

    from_agent_id: UUID
    project_id: UUID
    content: str = Field(..., min_length=1)
    message_type: str = "normal"
