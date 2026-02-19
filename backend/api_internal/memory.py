"""Internal memory endpoints (`update-memory`, `read-history`)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.models import Agent, AgentMessage
from backend.db.session import get_db

router = APIRouter(tags=["internal-memory"])


class UpdateMemoryRequest(BaseModel):
    agent_id: UUID
    content: str = Field(..., min_length=1)


@router.post("/update-memory")
async def update_memory(
    body: UpdateMemoryRequest,
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(auth_agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    result = await db.execute(select(Agent).where(Agent.id == body.agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.memory = {"content": body.content}
    await db.commit()
    return {"message": "Memory updated."}


@router.get("/read-history")
async def read_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_id: UUID | None = Query(None),
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AgentMessage)
        .where(AgentMessage.agent_id == UUID(auth_agent_id))
        .order_by(AgentMessage.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if session_id:
        q = q.where(AgentMessage.session_id == session_id)
    result = await db.execute(q)
    rows = list(result.scalars().all())
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "tool_name": m.tool_name,
            "tool_input": m.tool_input,
            "tool_output": m.tool_output,
            "created_at": m.created_at,
            "loop_iteration": m.loop_iteration,
        }
        for m in rows
    ]
