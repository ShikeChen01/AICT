"""
Internal messaging API for agent tools: send_message, broadcast_message.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.session import get_db
from backend.schemas.message import ChannelMessageResponse, InternalBroadcastMessage, InternalSendMessage
from backend.services.message_service import get_message_service

router = APIRouter(prefix="/messaging", tags=["internal-messaging"])


@router.post("/send", response_model=ChannelMessageResponse)
async def send_message(
    body: InternalSendMessage,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Send a message from an agent to a target (or broadcast if target_agent_id is null)."""
    if body.from_agent_id != UUID(agent_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="from_agent_id must match authenticated agent")
    service = get_message_service(db)
    if body.target_agent_id is None:
        msg = await service.broadcast(
            from_agent_id=body.from_agent_id,
            project_id=body.project_id,
            content=body.content,
            message_type=body.message_type,
        )
    else:
        msg = await service.send(
            from_agent_id=body.from_agent_id,
            target_agent_id=body.target_agent_id,
            project_id=body.project_id,
            content=body.content,
            message_type=body.message_type,
        )
    await db.commit()
    # Wake target agent if not broadcast
    if body.target_agent_id is not None:
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
    """Broadcast message (write only, no wake-up)."""
    if body.from_agent_id != UUID(agent_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="from_agent_id must match authenticated agent")
    service = get_message_service(db)
    msg = await service.broadcast(
        from_agent_id=body.from_agent_id,
        project_id=body.project_id,
        content=body.content,
        message_type=body.message_type,
    )
    await db.commit()
    return ChannelMessageResponse.model_validate(msg)
