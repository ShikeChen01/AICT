"""MCP server config endpoints — per-agent MCP server management.

CRUD for MCP server connections + tool discovery (sync).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Agent, McpServerConfig, User
from backend.db.repositories.mcp_servers import McpServerConfigRepository
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.tools.executors.mcp_bridge import discover_tools

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class McpServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=1)
    api_key: str | None = Field(default=None)
    headers: dict | None = Field(default=None)


class McpServerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    headers: dict | None = Field(default=None)
    enabled: bool | None = Field(default=None)


class McpServerResponse(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    url: str
    has_api_key: bool
    headers: dict | None
    enabled: bool
    status: str
    status_detail: str | None
    tool_count: int

    model_config = {"from_attributes": True}


class McpToolResponse(BaseModel):
    tool_name: str
    description: str
    input_schema: dict
    enabled: bool


class McpSyncResponse(BaseModel):
    status: str
    tools_discovered: int
    tools: list[McpToolResponse]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(server: McpServerConfig) -> dict:
    return {
        "id": server.id,
        "agent_id": server.agent_id,
        "name": server.name,
        "url": server.url,
        "has_api_key": server.api_key is not None,
        "headers": server.headers,
        "enabled": server.enabled,
        "status": server.status,
        "status_detail": server.status_detail,
        "tool_count": server.tool_count,
    }


async def _get_agent_with_access(
    db: AsyncSession, agent_id: UUID, user_id: UUID | None
) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user_id:
        await require_project_access(db, agent.project_id, user_id)
    return agent


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}", response_model=list[McpServerResponse])
async def list_mcp_servers(
    agent_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all MCP server configs for an agent."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_agent_with_access(db, agent_id, user_id)
    repo = McpServerConfigRepository(db)
    servers = await repo.list_for_agent(agent_id)
    return [_to_response(s) for s in servers]


@router.post("/agents/{agent_id}", response_model=McpServerResponse, status_code=201)
async def create_mcp_server(
    agent_id: UUID,
    body: McpServerCreate,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new MCP server connection for an agent."""
    user_id = current_user.id if isinstance(current_user, User) else None
    await _get_agent_with_access(db, agent_id, user_id)
    repo = McpServerConfigRepository(db)
    server = await repo.create(
        agent_id=agent_id,
        name=body.name,
        url=body.url,
        api_key=body.api_key,
        headers=body.headers,
    )
    await db.commit()
    return _to_response(server)


@router.put("/{server_id}", response_model=McpServerResponse)
async def update_mcp_server(
    server_id: UUID,
    body: McpServerUpdate,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing MCP server config."""
    user_id = current_user.id if isinstance(current_user, User) else None
    repo = McpServerConfigRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await _get_agent_with_access(db, server.agent_id, user_id)

    updated = await repo.update_server(
        server_id,
        name=body.name,
        url=body.url,
        api_key=body.api_key,
        headers=body.headers,
        enabled=body.enabled,
    )
    await db.commit()
    return _to_response(updated)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an MCP server and all its discovered tools."""
    user_id = current_user.id if isinstance(current_user, User) else None
    repo = McpServerConfigRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await _get_agent_with_access(db, server.agent_id, user_id)
    await repo.delete_server(server_id)
    await db.commit()


@router.post("/{server_id}/sync", response_model=McpSyncResponse)
async def sync_mcp_server_tools(
    server_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover tools from an MCP server and sync them into the agent's tool registry.

    Calls the remote server's tools/list endpoint, then upserts ToolConfig rows.
    New tools are added; removed tools are cleaned up; existing tools keep user edits.
    """
    user_id = current_user.id if isinstance(current_user, User) else None
    repo = McpServerConfigRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await _get_agent_with_access(db, server.agent_id, user_id)

    try:
        raw_tools = await discover_tools(server)
        tool_configs = await repo.sync_tools(server, raw_tools)
        await repo.update_status(
            server_id,
            status="connected",
            status_detail=None,
            tool_count=len(tool_configs),
        )
        await db.commit()
        return {
            "status": "connected",
            "tools_discovered": len(tool_configs),
            "tools": [
                {
                    "tool_name": tc.tool_name,
                    "description": tc.description,
                    "input_schema": tc.input_schema,
                    "enabled": tc.enabled,
                }
                for tc in tool_configs
            ],
        }
    except Exception as exc:
        error_msg = str(exc)
        await repo.update_status(
            server_id,
            status="error",
            status_detail=error_msg,
        )
        await db.commit()
        logger.warning(
            "MCP sync failed for server %s: %s", server.name, error_msg
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "MCP_SYNC_FAILED",
                "message": f"Failed to discover tools from '{server.name}': {error_msg}",
            },
        )
