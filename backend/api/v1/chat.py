"""
Chat REST API endpoints.

User-GM conversation interface.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.db.session import get_db
from backend.schemas.chat import ChatMessageCreate, ChatMessageResponse
from backend.services.chat_service import get_chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatResponse(ChatMessageResponse):
    """Extended response for chat send that includes both messages."""
    pass


class SendMessageResponse(ChatMessageResponse):
    """Response after sending a message - returns the GM response."""
    user_message: ChatMessageResponse | None = None


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    project_id: UUID = Query(..., description="Project ID"),
    limit: int = Query(100, ge=1, le=500, description="Max messages to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a project."""
    service = get_chat_service(db)
    messages = await service.get_history(project_id, limit, offset)
    return messages


@router.post("/send", response_model=SendMessageResponse, status_code=201)
async def send_message(
    data: ChatMessageCreate,
    project_id: UUID = Query(..., description="Project ID"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the GM and get the response.

    This is a synchronous endpoint for MVP-0 (no streaming).
    The GM processes the message and returns a complete response.
    """
    service = get_chat_service(db)
    user_msg, gm_msg = await service.send_message(project_id, data)
    gm_payload = ChatMessageResponse.model_validate(gm_msg)
    user_payload = ChatMessageResponse.model_validate(user_msg)
    return SendMessageResponse(
        **gm_payload.model_dump(),
        user_message=user_payload,
    )


@router.get("/message/{message_id}", response_model=ChatMessageResponse)
async def get_message(
    message_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single chat message by ID."""
    service = get_chat_service(db)
    return await service.get_message(message_id)
