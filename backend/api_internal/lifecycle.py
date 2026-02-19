"""Internal lifecycle contract (`/internal/agent/end|sleep|interrupt`)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent
from backend.db.session import get_db
from backend.workers.worker_manager import get_worker_manager

router = APIRouter(tags=["internal-lifecycle"])


class EndRequest(BaseModel):
    agent_id: uuid.UUID


class SleepRequest(BaseModel):
    agent_id: uuid.UUID
    duration_seconds: int = 0


class InterruptRequest(BaseModel):
    agent_id: uuid.UUID
    target_agent_id: uuid.UUID
    reason: str


async def _get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFoundError(str(agent_id))
    return agent


@router.post("/end")
async def end_agent(
    body: EndRequest,
    actor_agent_id: str = Depends(verify_agent_request),
):
    """Documented for completeness; loop handles actual END execution."""
    if str(body.agent_id) != actor_agent_id:
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    return {"message": "END acknowledged"}


@router.post("/sleep")
async def sleep_agent(
    body: SleepRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    """Set agent status to sleeping."""
    if str(body.agent_id) != actor_agent_id:
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    agent = await _get_agent(session, body.agent_id)
    agent.status = "sleeping"
    await session.commit()
    return {"agent_id": str(agent.id), "status": agent.status}


@router.post("/interrupt")
async def interrupt_agent(
    body: InterruptRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    """Interrupt target agent session (manager/cto only)."""
    if str(body.agent_id) != actor_agent_id:
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")

    actor = await _get_agent(session, body.agent_id)
    if actor.role not in {"manager", "cto"}:
        raise HTTPException(status_code=403, detail="Only manager/cto can interrupt")

    await _get_agent(session, body.target_agent_id)
    get_worker_manager().interrupt_agent(body.target_agent_id)
    return {"message": "Agent interrupted."}

