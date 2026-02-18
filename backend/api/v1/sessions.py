"""
Agent sessions REST API (docs: replaces jobs).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.db.models import AgentSession
from backend.db.session import get_db
from backend.schemas.session import AgentMessageResponse, AgentSessionResponse
from backend.services.session_service import get_session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[AgentSessionResponse])
async def list_sessions(
    project_id: UUID = Query(..., description="Project ID"),
    agent_id: UUID | None = Query(None, description="Filter by agent"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List sessions for a project, optionally filtered by agent. Most recent first."""
    service = get_session_service(db)
    sessions = await service.list_by_project(
        project_id=project_id,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return [AgentSessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=AgentSessionResponse)
async def get_session(
    session_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single session by ID."""
    result = await db.execute(select(AgentSession).where(AgentSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return AgentSessionResponse.model_validate(session)


@router.get("/{session_id}/messages", response_model=list[AgentMessageResponse])
async def get_session_messages(
    session_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get the persistent message log for a session (inspector/debug)."""
    result = await db.execute(select(AgentSession).where(AgentSession.id == session_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")
    service = get_session_service(db)
    messages = await service.get_session_messages(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return [AgentMessageResponse.model_validate(m) for m in messages]
