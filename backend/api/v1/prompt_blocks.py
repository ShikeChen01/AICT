"""Prompt block configuration endpoints.

Blocks are DB-backed (seeded at agent/template creation from .md files).
Users can edit content, reorder, duplicate, enable/disable, or reset to default.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Agent, AgentTemplate, PromptBlockConfig, User
from backend.db.repositories.agent_templates import (
    PromptBlockConfigRepository,
    _build_block_defs_for_role,
)
from backend.db.session import get_db

router = APIRouter(prefix="/prompt-blocks", tags=["prompt-blocks"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class PromptBlockResponse(BaseModel):
    id: UUID
    template_id: UUID | None
    agent_id: UUID | None
    block_key: str
    content: str
    position: int
    enabled: bool

    model_config = {"from_attributes": True}


class BlockConfigItem(BaseModel):
    block_key: str = Field(..., min_length=1, max_length=50)
    content: str = Field(default="")
    position: int = Field(default=0, ge=0)
    enabled: bool = Field(default=True)


class BulkSaveBlocksRequest(BaseModel):
    blocks: list[BlockConfigItem]


class DefaultBlockResponse(BaseModel):
    block_key: str
    content: str
    position: int
    enabled: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_agent_with_access(db: AsyncSession, agent_id: UUID, user_id: UUID | None) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user_id:
        await require_project_access(db, agent.project_id, user_id)
    return agent


async def _get_template_with_access(
    db: AsyncSession, template_id: UUID, user_id: UUID | None
) -> AgentTemplate:
    result = await db.execute(select(AgentTemplate).where(AgentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if user_id:
        await require_project_access(db, template.project_id, user_id)
    return template


# ── Agent-level block endpoints ────────────────────────────────────────────────

@router.get("/agents/{agent_id}/blocks", response_model=list[PromptBlockResponse])
async def list_agent_blocks(
    agent_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all prompt blocks for an agent, ordered by position."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_agent_with_access(db, agent_id, user_id)
    repo = PromptBlockConfigRepository(db)
    return await repo.list_for_agent(agent_id)


@router.put("/agents/{agent_id}/blocks", response_model=list[PromptBlockResponse])
async def bulk_save_agent_blocks(
    agent_id: UUID,
    body: BulkSaveBlocksRequest,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk replace all prompt blocks for an agent.

    Accepts the full ordered list of blocks. Deletes existing and inserts new.
    Use this for reordering, editing content, duplicating blocks, or toggling enabled.
    """
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_agent_with_access(db, agent_id, user_id)
    repo = PromptBlockConfigRepository(db)
    result = await repo.bulk_replace_agent_blocks(
        agent_id, [b.model_dump() for b in body.blocks]
    )
    await db.commit()
    return result


@router.post("/agents/{agent_id}/blocks/{block_id}/reset", response_model=PromptBlockResponse)
async def reset_agent_block(
    agent_id: UUID,
    block_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset a single agent block's content to the .md file default."""
    user_id = current_user.id if isinstance(current_user, User) else None
    agent = await _get_agent_with_access(db, agent_id, user_id)

    # Determine base_role from agent's role
    role_to_base = {"manager": "manager", "cto": "cto", "engineer": "worker"}
    base_role = role_to_base.get(agent.role, "worker")

    repo = PromptBlockConfigRepository(db)
    block = await repo.reset_agent_block_to_default(agent_id, block_id, base_role)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found for this agent")
    await db.commit()
    return block


# ── Template-level block endpoints ─────────────────────────────────────────────

@router.get("/templates/{template_id}/blocks", response_model=list[PromptBlockResponse])
async def list_template_blocks(
    template_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all prompt blocks for a template, ordered by position."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_template_with_access(db, template_id, user_id)
    repo = PromptBlockConfigRepository(db)
    return await repo.list_for_template(template_id)


@router.put("/templates/{template_id}/blocks", response_model=list[PromptBlockResponse])
async def bulk_save_template_blocks(
    template_id: UUID,
    body: BulkSaveBlocksRequest,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk replace all prompt blocks for a template."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_template_with_access(db, template_id, user_id)
    repo = PromptBlockConfigRepository(db)
    result = await repo.bulk_replace_template_blocks(
        template_id, [b.model_dump() for b in body.blocks]
    )
    await db.commit()
    return result


# ── Defaults endpoint ─────────────────────────────────────────────────────────

@router.get("/defaults/{base_role}", response_model=list[DefaultBlockResponse])
async def get_default_blocks(
    base_role: str,
    current_user: User | None = Depends(get_current_user),
):
    """Return the codebase default blocks for a given base_role.

    base_role: 'manager', 'cto', or 'worker'. Used for "Reset to Default" UI.
    """
    valid_roles = {"manager", "cto", "worker"}
    if base_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"base_role must be one of: {valid_roles}")
    return _build_block_defs_for_role(base_role)
