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
from backend.prompts.assembly import (
    BLOCK_REGISTRY,
    _CONDITIONAL_BLOCK_KEYS,
    _INCOMING_MSG_BUDGET_TOKENS,
    _MEMORY_RATIO,
    _PAST_SESSION_RATIO,
    _CHARS_PER_TOKEN,
    _TOOL_SCHEMA_RESERVE_TOKENS,
    estimate_tokens,
)
from backend.llm.model_catalog import (
    get_context_window,
    get_image_budget,
    get_image_tokens_per_image,
    model_supports_vision,
    is_claude_model,
    DEFAULT_CONTEXT_WINDOW,
)

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
    """List all prompt blocks for an agent, ordered by position.

    Auto-seeds default blocks from the role's .md definitions if the agent has
    none (covers agents created before the prompt-block system was added).
    """
    user_id = current_user.id if isinstance(current_user, User) else None
    agent = await _get_agent_with_access(db, agent_id, user_id)
    repo = PromptBlockConfigRepository(db)
    blocks = await repo.ensure_agent_blocks(agent_id, agent.role)
    await db.commit()
    return blocks


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


# ── Meta endpoint ──────────────────────────────────────────────────────────────

_CONDITIONAL_RESERVE_TOKENS = 1_500  # must match assembly.py


class BlockMetaResponse(BaseModel):
    kind: str
    max_chars: int | None
    truncation: str


class PromptMetaResponse(BaseModel):
    context_window_tokens: int
    total_budget_tokens: int  # context_window + image_reserve (image reserve outside 200k)
    static_overhead_tokens: int
    dynamic_pool_tokens: int
    # Dynamic section budgets (ratio-based, scale with model)
    memory_budget_tokens: int
    past_session_budget_tokens: int
    current_session_budget_tokens: int
    # Static section details
    system_prompt_tokens: int
    tool_schema_tokens: int
    incoming_msg_budget_tokens: int
    # Effective allocation percentages (from agent overrides or system defaults)
    memory_pct: float
    past_session_pct: float
    current_session_pct: float
    # System defaults (for reset)
    default_memory_pct: float
    default_past_session_pct: float
    default_current_session_pct: float
    default_incoming_msg_tokens: int
    # Image input budget (outside context_window; total_budget_tokens = context_window + image_reserve)
    image_tokens_per_image: int       # per-image token cost for this model (0 = not vision-capable)
    image_default_max_images: int     # system-wide default image cap
    image_effective_max_images: int   # agent override or system default
    image_reserve_tokens: int         # total image budget = tokens_per_image × effective_max_images
    model_supports_vision: bool       # True if model can accept image inputs
    # Registry
    block_registry: dict[str, BlockMetaResponse]


@router.get("/meta", response_model=PromptMetaResponse)
async def get_prompt_meta(
    model: str | None = Query(default=None, description="Model name for window-specific budgets"),
    agent_id: UUID | None = Query(default=None, description="Agent ID to load blocks/tools for"),
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return context window budget constants and block registry metadata.

    Accepts optional ?model= and ?agent_id= query params.
    Returns model-specific budgets and tool schema token counts.
    Used by the frontend Prompt Builder dashboard.
    """
    import json as _json
    from backend.tools.loop_registry import get_tool_defs_for_role

    context_window = get_context_window(model or "") if model else DEFAULT_CONTEXT_WINDOW

    # Compute system prompt tokens from actual agent blocks (or estimate if no agent)
    system_prompt_tokens = 3_500  # conservative default estimate (excl. conditional blocks)
    tool_schema_tokens_measured = _TOOL_SCHEMA_RESERVE_TOKENS  # matches the assembly floor

    # Per-agent allocation overrides (filled in below if agent found)
    agent_alloc: dict = {}
    resolved_model = model or ""

    if agent_id is not None:
        user_id = current_user.id if isinstance(current_user, User) else None
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent:
            if user_id:
                await require_project_access(db, agent.project_id, user_id)

            # Use agent model if no model param provided
            if not model:
                resolved_model = agent.model or ""
                context_window = get_context_window(resolved_model)

            # Read per-agent allocation overrides
            agent_alloc = agent.token_allocations or {}

            # Measure system prompt from actual blocks (rough estimate without memory).
            # Excludes conditional blocks (injected at runtime as messages, not system prompt)
            # and stage blocks (only one is active at a time, managed separately).
            repo = PromptBlockConfigRepository(db)
            blocks = await repo.list_for_agent(agent_id)
            _STAGE_BLOCKS = frozenset({"thinking_stage", "execution_stage"})
            enabled_content = "\n\n".join(
                b.content for b in blocks
                if b.enabled
                and b.block_key not in _CONDITIONAL_BLOCK_KEYS
                and b.block_key not in _STAGE_BLOCKS
            )
            system_prompt_tokens = estimate_tokens(enabled_content)

            # Measure tool schema tokens from DB tool configs; apply the same floor
            # as assembly.py so the budget chart matches the actual runtime reservation.
            from backend.db.repositories.tool_configs import ToolConfigRepository
            tool_repo = ToolConfigRepository(db)
            role_map = {"manager": "manager", "cto": "cto", "engineer": "worker"}
            base_role = role_map.get(agent.role, "worker")
            tool_configs = await tool_repo.ensure_agent_tools(agent_id, base_role)
            measured = sum(
                len(_json.dumps({
                    "name": tc.tool_name,
                    "description": tc.description,
                    "input_schema": tc.input_schema or {},
                })) // _CHARS_PER_TOKEN
                for tc in tool_configs if tc.enabled
            )
            tool_schema_tokens_measured = max(measured, _TOOL_SCHEMA_RESERVE_TOKENS)

    # Resolve effective allocation values (agent overrides or system defaults)
    default_memory_pct = _MEMORY_RATIO * 100          # 10.0
    default_past_pct = _PAST_SESSION_RATIO * 100       # 12.0
    default_current_pct = (1.0 - _MEMORY_RATIO - _PAST_SESSION_RATIO) * 100  # 78.0
    default_incoming = _INCOMING_MSG_BUDGET_TOKENS     # 8000

    effective_memory_pct = float(agent_alloc.get("memory_pct", default_memory_pct))
    effective_past_pct = float(agent_alloc.get("past_session_pct", default_past_pct))
    effective_current_pct = float(agent_alloc.get("current_session_pct", default_current_pct))
    effective_incoming = int(agent_alloc.get("incoming_msg_tokens", default_incoming))

    # Image budget
    _DEFAULT_MAX_IMAGES = 10
    effective_max_images = int(agent_alloc.get("max_images_per_turn", _DEFAULT_MAX_IMAGES))
    image_tpi = get_image_tokens_per_image(resolved_model)
    image_reserve = get_image_budget(resolved_model, effective_max_images)
    vision_supported = model_supports_vision(resolved_model)

    static_overhead = (
        system_prompt_tokens
        + tool_schema_tokens_measured
        + effective_incoming
        + _CONDITIONAL_RESERVE_TOKENS
    )
    dynamic_pool = max(0, context_window - static_overhead)
    total_budget_tokens = context_window + image_reserve

    memory_budget = int(dynamic_pool * effective_memory_pct / 100.0)
    past_session_budget = int(dynamic_pool * effective_past_pct / 100.0)
    current_session_budget = dynamic_pool - memory_budget - past_session_budget

    return PromptMetaResponse(
        context_window_tokens=context_window,
        total_budget_tokens=total_budget_tokens,
        static_overhead_tokens=static_overhead,
        dynamic_pool_tokens=dynamic_pool,
        memory_budget_tokens=memory_budget,
        past_session_budget_tokens=past_session_budget,
        current_session_budget_tokens=current_session_budget,
        system_prompt_tokens=system_prompt_tokens,
        tool_schema_tokens=tool_schema_tokens_measured,
        incoming_msg_budget_tokens=effective_incoming,
        memory_pct=effective_memory_pct,
        past_session_pct=effective_past_pct,
        current_session_pct=effective_current_pct,
        default_memory_pct=default_memory_pct,
        default_past_session_pct=default_past_pct,
        default_current_session_pct=default_current_pct,
        default_incoming_msg_tokens=default_incoming,
        image_tokens_per_image=image_tpi,
        image_default_max_images=_DEFAULT_MAX_IMAGES,
        image_effective_max_images=effective_max_images,
        image_reserve_tokens=image_reserve,
        model_supports_vision=vision_supported,
        block_registry={
            key: BlockMetaResponse(kind=meta.kind, max_chars=meta.max_chars, truncation=meta.truncation)
            for key, meta in BLOCK_REGISTRY.items()
        },
    )
