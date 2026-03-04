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
from backend.db.models import Agent, SandboxConfig, User
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


async def _get_agent(db: AsyncSession, agent_id: UUID, user_id: UUID) -> Agent:
    """Load an agent and verify project access (no sandbox required)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await require_project_access(db, agent.project_id, user_id)
    return agent


class SandboxInfo(BaseModel):
    agent_id: str
    agent_name: str
    agent_role: str
    sandbox_id: str
    persistent: bool
    status: str | None = None
    sandbox_config_id: str | None = None
    sandbox_config_name: str | None = None


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

    # Batch-load config names for agents that have one
    config_ids = {a.sandbox_config_id for a in agents if a.sandbox_config_id}
    config_names: dict[UUID, str] = {}
    if config_ids:
        cfg_result = await db.execute(
            select(SandboxConfig.id, SandboxConfig.name)
            .where(SandboxConfig.id.in_(config_ids))
        )
        config_names = {row.id: row.name for row in cfg_result.all()}

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
            sandbox_config_id=str(agent.sandbox_config_id) if agent.sandbox_config_id else None,
            sandbox_config_name=config_names.get(agent.sandbox_config_id) if agent.sandbox_config_id else None,
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


@router.post("/{agent_id}/apply-config")
async def apply_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run the agent's assigned sandbox config setup script on its running sandbox."""
    agent = await _get_agent_with_sandbox(db, agent_id, current_user.id)
    svc = _get_sandbox_service()
    return await svc.apply_config(db, agent)


@router.post("/{agent_id}/reset")
async def reset_sandbox(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Destroy the agent's current sandbox and create a fresh one.

    Use this when the user wants a clean slate — the old container and volume
    are destroyed, a new sandbox is created, and (if the agent has a config
    assigned) the setup script runs on the new sandbox.
    """
    agent = await _get_agent(db, agent_id, current_user.id)
    svc = _get_sandbox_service()

    # Destroy old sandbox if one exists
    if agent.sandbox_id:
        await svc.destroy_sandbox(db, agent)

    # Create fresh sandbox
    meta = await svc.ensure_running_sandbox(db, agent, persistent=bool(agent.sandbox_persist))
    await db.commit()
    return {
        "ok": True,
        "sandbox_id": meta.sandbox_id,
        "status": meta.status,
        "message": f"Fresh sandbox created: {meta.sandbox_id}",
    }


class ReassignRequest(BaseModel):
    target_agent_id: UUID


@router.post("/{agent_id}/reassign")
async def reassign_sandbox(
    agent_id: UUID,
    body: ReassignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reassign an agent's sandbox to a different agent.

    The source agent loses its sandbox, and the target agent gets it.
    Useful when users want to reuse a configured sandbox environment
    with a different agent.
    """
    source_agent = await _get_agent_with_sandbox(db, agent_id, current_user.id)
    target_agent = await _get_agent(db, body.target_agent_id, current_user.id)

    if target_agent.sandbox_id:
        raise HTTPException(
            status_code=409,
            detail="Target agent already has a sandbox. Destroy it first.",
        )

    # Transfer sandbox ownership
    sandbox_id = source_agent.sandbox_id
    source_agent.sandbox_id = None
    target_agent.sandbox_id = sandbox_id
    target_agent.sandbox_persist = source_agent.sandbox_persist

    await db.commit()

    # Re-assign in pool manager
    svc = _get_sandbox_service()
    try:
        await svc._pool.session_end(str(source_agent.id))
    except Exception:
        pass  # Source may not have an active session
    try:
        await svc.ensure_running_sandbox(db, target_agent)
        await db.commit()
    except Exception:
        pass  # Best-effort — the sandbox_id is already on the target agent

    return {
        "ok": True,
        "sandbox_id": sandbox_id,
        "source_agent_id": str(agent_id),
        "target_agent_id": str(body.target_agent_id),
    }
