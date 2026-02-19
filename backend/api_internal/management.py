"""Internal management endpoints (`spawn-engineer`, `list-agents`)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.models import Agent
from backend.db.session import get_db
from backend.services.agent_service import get_agent_service
from backend.workers.worker_manager import get_worker_manager

router = APIRouter(tags=["internal-management"])


class SpawnEngineerRequest(BaseModel):
    agent_id: UUID
    display_name: str
    model: str | None = None


@router.post("/spawn-engineer")
async def spawn_engineer(
    body: SpawnEngineerRequest,
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(auth_agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")

    result = await db.execute(select(Agent).where(Agent.id == body.agent_id))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Agent not found")
    if actor.role != "manager":
        raise HTTPException(status_code=403, detail="Only manager can spawn engineers")

    service = get_agent_service(db)
    agent = await service.spawn_engineer(
        actor.project_id,
        display_name=body.display_name,
        model=body.model or "claude-4.5",
    )
    await db.commit()
    await db.refresh(agent)
    await get_worker_manager().spawn_worker(agent.id, agent.project_id)
    return {"id": str(agent.id), "display_name": agent.display_name, "status": agent.status}


@router.get("/list-agents")
async def list_agents(
    project_id: UUID = Query(...),
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == UUID(auth_agent_id)))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Agent not found")
    if actor.role not in {"manager", "cto"}:
        raise HTTPException(status_code=403, detail="Only manager/cto can list agents")

    role_order = case(
        (Agent.role == "manager", 0),
        (Agent.role == "cto", 1),
        (Agent.role == "engineer", 2),
        else_=3,
    )
    result = await db.execute(
        select(Agent).where(Agent.project_id == project_id).order_by(role_order, Agent.display_name)
    )
    agents = list(result.scalars().all())
    return [
        {
            "id": str(a.id),
            "role": a.role,
            "display_name": a.display_name,
            "status": a.status,
            "current_task_id": str(a.current_task_id) if a.current_task_id else None,
        }
        for a in agents
    ]
