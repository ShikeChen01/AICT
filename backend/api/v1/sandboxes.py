"""
Sandboxes REST API — user-facing sandbox management endpoints.

Allows users to list, restart, toggle persistence, and destroy sandboxes
for agents in their projects.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Agent, User
from backend.db.session import get_db
from backend.services.sandbox_service import SandboxService

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def _get_sandbox_service() -> SandboxService:
    return SandboxService()


async def _get_agent_with_sandbox(
    db: AsyncSession, agent_id: UUID, user_id: UUID,
) -> Agent:
    """Load an agent and verify project access."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await require_project_access(db, agent.project_id, user_id)
    if not agent.sandbox_id:
        raise HTTPException(status_code=404, detail="Agent has no sandbox")
    return agent


class SandboxInfo(BaseModel):
    agent_id: str
    agent_name: str
    agent_role: str
    sandbox_id: str
    persistent: bool
    status: str | None = None


@router.get("", response_model=list[SandboxInfo])
async def list_sandboxes(
    project_id: UUID = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents with sandboxes for a project."""
    await require_project_access(db, project_id, current_user.id)

    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id, Agent.sandbox_id.isnot(None))
    )
    agents = result.scalars().all()

    # Fetch pool manager status for enrichment
    svc = _get_sandbox_service()
    pool_sandboxes = {}
    try:
        raw = await svc.list_all_sandboxes()
        pool_sandboxes = {s["sandbox_id"]: s for s in raw}
    except Exception:
        pass  # Pool manager may be unreachable — return what we know from DB

    items: list[SandboxInfo] = []
    for agent in agents:
        pool_info = pool_sandboxes.get(agent.sandbox_id, {})
        items.append(SandboxInfo(
            agent_id=str(agent.id),
            agent_name=agent.display_name or agent.role,
            agent_role=agent.role,
            sandbox_id=agent.sandbox_id,
            persistent=bool(agent.sandbox_persist),
            status=pool_info.get("status"),
        ))

    return items


class PersistentToggle(BaseModel):
    persistent: bool


@router.post("/{agent_id}/persistent")
async def toggle_persistent(
    agent_id: UUID,
    body: PersistentToggle,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the persistent flag on an agent's sandbox."""
    agent = await _get_agent_with_sandbox(db, agent_id, current_user.id)
    svc = _get_sandbox_service()
    result = await svc.set_sandbox_persistent(db, agent, body.persistent)
    await db.commit()
    return result


@router.post("/{agent_id}/restart")
async def restart_sandbox(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restart an agent's sandbox container (keeps volume / installed apps)."""
    agent = await _get_agent_with_sandbox(db, agent_id, current_user.id)
    svc = _get_sandbox_service()
    return await svc.restart_sandbox(agent)


@router.delete("/{agent_id}")
async def destroy_sandbox(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently destroy an agent's sandbox and its volume."""
    agent = await _get_agent_with_sandbox(db, agent_id, current_user.id)
    svc = _get_sandbox_service()
    result = await svc.destroy_sandbox(db, agent)
    await db.commit()
    return result
