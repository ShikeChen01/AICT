"""
Sandbox Configs REST API — user-level sandbox configuration profiles.

Users create, list, update, and delete sandbox configs (setup scripts)
that can be assigned to agents.  Configs are user-owned and reusable
across projects.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.db.models import Agent, SandboxConfig, User
from backend.db.session import get_db

router = APIRouter(prefix="/sandbox-configs", tags=["sandbox-configs"])


# ── Request / response schemas ────────────────────────────────────────


class SandboxConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    setup_script: str = ""


class SandboxConfigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    setup_script: str | None = None


class SandboxConfigResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    setup_script: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AssignConfigRequest(BaseModel):
    config_id: UUID | None = None  # None = unassign


# ── CRUD endpoints ────────────────────────────────────────────────────


@router.get("", response_model=list[SandboxConfigResponse])
async def list_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sandbox configs owned by the current user."""
    result = await db.execute(
        select(SandboxConfig)
        .where(SandboxConfig.user_id == current_user.id)
        .order_by(SandboxConfig.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=SandboxConfigResponse, status_code=201)
async def create_config(
    body: SandboxConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new sandbox config."""
    config = SandboxConfig(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        setup_script=body.setup_script,
    )
    db.add(config)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A config named '{body.name}' already exists",
        )
    await db.refresh(config)
    return config


@router.get("/{config_id}", response_model=SandboxConfigResponse)
async def get_config(
    config_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a sandbox config by ID."""
    config = await _get_user_config(db, config_id, current_user.id)
    return config


@router.patch("/{config_id}", response_model=SandboxConfigResponse)
async def update_config(
    config_id: UUID,
    body: SandboxConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a sandbox config."""
    config = await _get_user_config(db, config_id, current_user.id)
    if body.name is not None:
        config.name = body.name
    if body.description is not None:
        config.description = body.description
    if body.setup_script is not None:
        config.setup_script = body.setup_script
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A config named '{body.name}' already exists",
        )
    await db.refresh(config)
    return config


@router.delete("/{config_id}", status_code=204)
async def delete_config(
    config_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a sandbox config.  Agents using it will have their config unlinked."""
    config = await _get_user_config(db, config_id, current_user.id)
    await db.delete(config)
    await db.commit()


# ── Assign config to agent ────────────────────────────────────────────


@router.post("/assign/{agent_id}")
async def assign_config_to_agent(
    agent_id: UUID,
    body: AssignConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign (or unassign) a sandbox config to an agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.config_id is not None:
        # Verify the config exists and belongs to this user
        await _get_user_config(db, body.config_id, current_user.id)

    agent.sandbox_config_id = body.config_id
    await db.commit()
    return {"ok": True, "agent_id": str(agent_id), "config_id": str(body.config_id) if body.config_id else None}


# ── Helpers ────────────────────────────────────────────────────────────


async def _get_user_config(
    db: AsyncSession, config_id: UUID, user_id: UUID
) -> SandboxConfig:
    result = await db.execute(
        select(SandboxConfig).where(
            SandboxConfig.id == config_id,
            SandboxConfig.user_id == user_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Sandbox config not found")
    return config
