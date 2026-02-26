"""
Messages REST API: user-to-agent messaging.

POST /messages/send (202), GET /messages (conversation), GET /messages/all (activity).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import User
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.schemas.message import ChannelMessageResponse, ChannelMessageSend
from backend.services.message_service import get_message_service

logger = get_logger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post(
    "/send",
    response_model=ChannelMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    body: ChannelMessageSend,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message from the user to an agent. Fire-and-forget (202).
    The agent wakes up if sleeping; response arrives via WebSocket.
    """
    await require_project_access(db, body.project_id, current_user.id)
    service = get_message_service(db)
    msg = await service.send_user_to_agent(
        target_agent_id=body.target_agent_id,
        project_id=body.project_id,
        content=body.content,
        user_id=current_user.id,
    )
    await db.commit()
    logger.info(
        "send_message: msg_id=%s project=%s target_agent=%s content_len=%d",
        msg.id,
        body.project_id,
        body.target_agent_id,
        len(body.content),
    )
    # Notify MessageRouter to wake the agent (if router is available)
    try:
        from backend.workers.message_router import get_message_router
        get_message_router().notify(body.target_agent_id)
    except Exception as exc:
        logger.warning(
            "send_message: failed to notify router for agent %s: %s",
            body.target_agent_id,
            exc,
        )
    return ChannelMessageResponse.model_validate(msg)


@router.get("", response_model=list[ChannelMessageResponse])
async def list_conversation(
    project_id: UUID = Query(..., description="Project ID"),
    agent_id: UUID = Query(..., description="Agent ID (conversation partner)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Messages between the user and a specific agent (conversation view)."""
    await require_project_access(db, project_id, current_user.id)
    service = get_message_service(db)
    messages = await service.list_conversation(
        project_id=project_id, agent_id=agent_id, limit=limit, offset=offset
    )
    return [ChannelMessageResponse.model_validate(m) for m in messages]


@router.get("/all", response_model=list[ChannelMessageResponse])
async def list_all_messages(
    project_id: UUID = Query(..., description="Project ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All messages to/from the user in the project (activity view)."""
    await require_project_access(db, project_id, current_user.id)
    service = get_message_service(db)
    messages = await service.list_all_user_messages(
        project_id=project_id, limit=limit, offset=offset
    )
    return [ChannelMessageResponse.model_validate(m) for m in messages]
