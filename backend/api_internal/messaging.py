"""Internal agent messaging contract (`/internal/agent/*`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.session import get_db
from backend.schemas.message import (
    ChannelMessageResponse,
    InternalBroadcastMessage,
    InternalSendMessage,
)
from backend.services.message_service import get_message_service

router = APIRouter(tags=["internal-messaging"])


class MarkReceivedRequest(BaseModel):
    message_ids: list[UUID] = Field(default_factory=list)


def _authenticated_agent_uuid(agent_id: str) -> UUID:
    """Parse and validate authenticated agent header value."""
    try:
        return UUID(agent_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid X-Agent-ID header") from exc


@router.post("/send-message", response_model=ChannelMessageResponse)
async def send_message(
    body: InternalSendMessage,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Send an agent-to-agent (or agent-to-user) message and wake the target."""
    auth_agent_id = _authenticated_agent_uuid(agent_id)
    if body.from_agent_id != auth_agent_id:
        raise HTTPException(
            status_code=403,
            detail="from_agent_id must match authenticated agent",
        )

    if body.target_agent_id is None:
        raise HTTPException(status_code=400, detail="target_agent_id is required")

    service = get_message_service(db)
    msg = await service.send(
        from_agent_id=body.from_agent_id,
        target_agent_id=body.target_agent_id,
        project_id=body.project_id,
        content=body.content,
        message_type=body.message_type,
    )
    await db.commit()

    try:
        from backend.workers.message_router import get_message_router

        get_message_router().notify(body.target_agent_id)
    except Exception:
        pass
    return ChannelMessageResponse.model_validate(msg)


@router.post("/broadcast", response_model=ChannelMessageResponse)
async def broadcast_message(
    body: InternalBroadcastMessage,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Broadcast message without waking targets."""
    auth_agent_id = _authenticated_agent_uuid(agent_id)
    if body.from_agent_id != auth_agent_id:
        raise HTTPException(
            status_code=403,
            detail="from_agent_id must match authenticated agent",
        )
    service = get_message_service(db)
    msg = await service.broadcast(
        from_agent_id=body.from_agent_id,
        project_id=body.project_id,
        content=body.content,
        message_type=body.message_type,
    )
    await db.commit()
    return ChannelMessageResponse.model_validate(msg)


@router.get("/read-messages", response_model=list[ChannelMessageResponse])
async def read_messages(
    status: str = Query("sent"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Return unread/sent messages for the authenticated agent."""
    auth_agent_id = _authenticated_agent_uuid(agent_id)
    service = get_message_service(db)
    if status != "sent":
        return []
    messages = await service.get_unread_for_agent(
        target_agent_id=auth_agent_id,
        limit=limit,
        offset=offset,
    )
    return [ChannelMessageResponse.model_validate(m) for m in messages]


@router.post("/mark-received")
async def mark_received(
    body: MarkReceivedRequest,
    _agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Mark messages as received after loop ingestion."""
    service = get_message_service(db)
    await service.mark_received(body.message_ids)
    await db.commit()
    return {"updated": len(body.message_ids)}
