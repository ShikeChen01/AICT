"""Tool config endpoints — per-agent customizable tool definitions.

Users can edit tool description, detailed_description, enabled, and position.
Structural fields (tool_name, input_schema, allowed_roles) are read-only.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Agent, User
from backend.db.repositories.tool_configs import ToolConfigRepository
from backend.db.session import get_db
from backend.llm.model_catalog import get_context_window

router = APIRouter(prefix="/tool-configs", tags=["tool-configs"])

_CHARS_PER_TOKEN = 4
_MAX_TOOL_SCHEMA_PCT = 0.05  # tools may not exceed 5% of context window


# ── Schemas ────────────────────────────────────────────────────────────────────

class ToolConfigResponse(BaseModel):
    id: UUID
    agent_id: UUID | None
    template_id: UUID | None
    tool_name: str
    description: str
    detailed_description: str | None
    input_schema: dict
    allowed_roles: list[str]
    enabled: bool
    position: int
    estimated_tokens: int = 0
    source: str = "native"
    mcp_server_id: UUID | None = None

    model_config = {"from_attributes": True}


class ToolConfigUpdateItem(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="")
    detailed_description: str | None = Field(default=None)
    enabled: bool = Field(default=True)
    position: int = Field(default=0, ge=0)


class BulkSaveToolsRequest(BaseModel):
    tools: list[ToolConfigUpdateItem]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _estimate_tool_schema_tokens(items: list) -> int:
    """Estimate token cost for all enabled tool schemas."""
    total_chars = 0
    for t in items:
        if not getattr(t, "enabled", True):
            continue
        schema = t.input_schema if hasattr(t, "input_schema") else t.get("input_schema", {})
        desc = t.description if hasattr(t, "description") else t.get("description", "")
        name = t.tool_name if hasattr(t, "tool_name") else t.get("tool_name", "")
        total_chars += len(json.dumps({"name": name, "description": desc, "input_schema": schema}))
    return total_chars // _CHARS_PER_TOKEN


async def _get_agent_with_access(db: AsyncSession, agent_id: UUID, user_id: UUID | None) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user_id:
        await require_project_access(db, agent.project_id, user_id)
    return agent


def _enrich_with_tokens(tc) -> dict:
    """Add estimated_tokens to a ToolConfig row for the API response."""
    schema = tc.input_schema or {}
    chars = len(json.dumps({
        "name": tc.tool_name,
        "description": tc.description,
        "input_schema": schema,
    }))
    tokens = chars // _CHARS_PER_TOKEN
    return {
        "id": tc.id,
        "agent_id": tc.agent_id,
        "template_id": tc.template_id,
        "tool_name": tc.tool_name,
        "description": tc.description,
        "detailed_description": tc.detailed_description,
        "input_schema": tc.input_schema or {},
        "allowed_roles": tc.allowed_roles or ["*"],
        "enabled": tc.enabled,
        "position": tc.position,
        "estimated_tokens": tokens,
        "source": getattr(tc, "source", "native") or "native",
        "mcp_server_id": getattr(tc, "mcp_server_id", None),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/tools", response_model=list[ToolConfigResponse])
async def list_agent_tools(
    agent_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tool configs for an agent, ordered by position.

    Auto-seeds defaults from tool_descriptions.json if the agent has none.
    """
    user_id = current_user.id if isinstance(current_user, User) else None
    agent = await _get_agent_with_access(db, agent_id, user_id)
    repo = ToolConfigRepository(db)
    role_map = {"manager": "manager", "cto": "cto", "engineer": "worker"}
    base_role = role_map.get(agent.role, "worker")
    tools = await repo.ensure_agent_tools(agent_id, base_role)
    await db.commit()
    return [_enrich_with_tokens(t) for t in tools]


@router.put("/agents/{agent_id}/tools", response_model=list[ToolConfigResponse])
async def bulk_save_agent_tools(
    agent_id: UUID,
    body: BulkSaveToolsRequest,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update tool descriptions, enabled status, and position.

    Returns 422 TOOL_SCHEMA_BUDGET_EXCEEDED if total enabled tool schema tokens
    exceed 5% of the agent's model context window.
    """
    user_id = current_user.id if isinstance(current_user, User) else None
    agent = await _get_agent_with_access(db, agent_id, user_id)

    # Validate tool schema budget using actual input_schema from DB
    repo = ToolConfigRepository(db)
    existing = {tc.tool_name: tc for tc in await repo.list_for_agent(agent_id)}
    new_total_tokens = 0
    for item in body.tools:
        if not item.enabled:
            continue
        tc = existing.get(item.tool_name)
        schema = tc.input_schema if tc else {}
        chars = len(json.dumps({
            "name": item.tool_name,
            "description": item.description,
            "input_schema": schema,
        }))
        new_total_tokens += chars // _CHARS_PER_TOKEN

    context_window = get_context_window(agent.model or "")
    max_tool_tokens = int(context_window * _MAX_TOOL_SCHEMA_PCT)

    if new_total_tokens > max_tool_tokens:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "TOOL_SCHEMA_BUDGET_EXCEEDED",
                "message": (
                    f"Tool descriptions total {new_total_tokens:,} tokens, exceeding the "
                    f"{max_tool_tokens:,} token limit (5% of {context_window:,} context window). "
                    "Shorten tool descriptions or disable unused tools."
                ),
                "current_tokens": new_total_tokens,
                "max_tokens": max_tool_tokens,
            },
        )

    updates = [item.model_dump() for item in body.tools]
    tools = await repo.bulk_update_agent_tools(agent_id, updates)
    await db.commit()
    return [_enrich_with_tokens(t) for t in tools]

@router.post("/agents/{agent_id}/tools/{tool_config_id}/reset", response_model=ToolConfigResponse)
async def reset_agent_tool(
    agent_id: UUID,
    tool_config_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset a single tool config to its tool_descriptions.json defaults."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_agent_with_access(db, agent_id, user_id)
    repo = ToolConfigRepository(db)
    tc = await repo.reset_to_default(agent_id, tool_config_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Tool config not found for this agent")
    await db.commit()
    return _enrich_with_tokens(tc)


@router.get("/meta")
async def get_tool_configs_meta(
    agent_id: UUID = Query(..., description="Agent ID to compute meta for"),
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregate token estimate and budget info for an agent's tool configs."""
    user_id = current_user.id if isinstance(current_user, User) else None
    agent = await _get_agent_with_access(db, agent_id, user_id)
    repo = ToolConfigRepository(db)
    role_map = {"manager": "manager", "cto": "cto", "engineer": "worker"}
    base_role = role_map.get(agent.role, "worker")
    tools = await repo.ensure_agent_tools(agent_id, base_role)
    await db.commit()

    enabled = [t for t in tools if t.enabled]
    total_tokens = _estimate_tool_schema_tokens(enabled)
    context_window = get_context_window(agent.model or "")
    max_tool_tokens = int(context_window * _MAX_TOOL_SCHEMA_PCT)

    return {
        "total_tools": len(tools),
        "enabled_tools": len(enabled),
        "total_tokens": total_tokens,
        "max_tokens": max_tool_tokens,
        "budget_pct_used": round(total_tokens / max_tool_tokens, 4) if max_tool_tokens else 0,
        "context_window_tokens": context_window,
    }
