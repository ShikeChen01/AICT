"""
Internal agent lifecycle endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent
from backend.db.session import get_db
from backend.services.orchestrator import OrchestratorService

router = APIRouter(prefix="/lifecycle", tags=["internal-lifecycle"])
orchestrator = OrchestratorService()


class AgentLifecycleRequest(BaseModel):
    target_agent_id: str


class AgentLifecycleResponse(BaseModel):
    actor_agent_id: str
    target_agent_id: str
    status: str
    sandbox_id: str | None


async def _get_agent(session: AsyncSession, agent_id: str) -> Agent:
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError as exc:
        raise AgentNotFoundError(agent_id) from exc
    result = await session.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFoundError(agent_id)
    return agent


@router.post("/wake", response_model=AgentLifecycleResponse)
async def wake_agent(
    req: AgentLifecycleRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    target = await _get_agent(session, req.target_agent_id)
    target.status = "active"
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, target)
    return AgentLifecycleResponse(
        actor_agent_id=actor_agent_id,
        target_agent_id=str(target.id),
        status=target.status,
        sandbox_id=sandbox.sandbox_id,
    )


@router.post("/sleep", response_model=AgentLifecycleResponse)
async def sleep_agent(
    req: AgentLifecycleRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    target = await _get_agent(session, req.target_agent_id)
    target.status = "sleeping"
    await orchestrator.close_if_ephemeral(session, target)
    return AgentLifecycleResponse(
        actor_agent_id=actor_agent_id,
        target_agent_id=str(target.id),
        status=target.status,
        sandbox_id=target.sandbox_id,
    )


@router.post("/restart", response_model=AgentLifecycleResponse)
async def restart_agent(
    req: AgentLifecycleRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    target = await _get_agent(session, req.target_agent_id)
    if target.sandbox_id:
        await orchestrator.e2b_service.close_sandbox(session, target)
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, target)
    target.status = "active"
    return AgentLifecycleResponse(
        actor_agent_id=actor_agent_id,
        target_agent_id=str(target.id),
        status=target.status,
        sandbox_id=sandbox.sandbox_id,
    )


@router.get("/status/{target_agent_id}", response_model=AgentLifecycleResponse)
async def get_status(
    target_agent_id: str,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    target = await _get_agent(session, target_agent_id)
    return AgentLifecycleResponse(
        actor_agent_id=actor_agent_id,
        target_agent_id=str(target.id),
        status=target.status,
        sandbox_id=target.sandbox_id,
    )

