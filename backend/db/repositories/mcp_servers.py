"""Repository for McpServerConfig — per-agent MCP server connections."""

from __future__ import annotations

import uuid
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import McpServerConfig, ToolConfig
from backend.db.repositories.base import BaseRepository


def _encrypt(plaintext: str) -> bytes:
    """Fernet-encrypt a string value."""
    f = Fernet(settings.secret_encryption_key.encode())
    return f.encrypt(plaintext.encode())


class McpServerConfigRepository(BaseRepository[McpServerConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(McpServerConfig, session)

    async def list_for_agent(self, agent_id: UUID) -> list[McpServerConfig]:
        """Return all MCP server configs for an agent, ordered by name."""
        result = await self.session.execute(
            select(McpServerConfig)
            .where(McpServerConfig.agent_id == agent_id)
            .order_by(McpServerConfig.name)
        )
        return list(result.scalars().all())

    async def list_enabled_for_agent(self, agent_id: UUID) -> list[McpServerConfig]:
        """Return only enabled MCP servers for an agent."""
        result = await self.session.execute(
            select(McpServerConfig)
            .where(
                McpServerConfig.agent_id == agent_id,
                McpServerConfig.enabled.is_(True),
            )
            .order_by(McpServerConfig.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, server_id: UUID) -> McpServerConfig | None:
        result = await self.session.execute(
            select(McpServerConfig).where(McpServerConfig.id == server_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        agent_id: UUID,
        name: str,
        url: str,
        api_key: str | None = None,
        headers: dict | None = None,
    ) -> McpServerConfig:
        """Create a new MCP server config for an agent."""
        encrypted_key = _encrypt(api_key) if api_key else None
        server = McpServerConfig(
            id=uuid.uuid4(),
            agent_id=agent_id,
            name=name,
            url=url,
            api_key=encrypted_key,
            headers=headers,
            enabled=True,
            status="disconnected",
            tool_count=0,
        )
        self.session.add(server)
        await self.session.flush()
        return server

    async def update_server(
        self,
        server_id: UUID,
        *,
        name: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        headers: dict | None = None,
        enabled: bool | None = None,
    ) -> McpServerConfig | None:
        """Update mutable fields on an MCP server config."""
        server = await self.get_by_id(server_id)
        if not server:
            return None
        if name is not None:
            server.name = name
        if url is not None:
            server.url = url
        if api_key is not None:
            server.api_key = _encrypt(api_key)
        if headers is not None:
            server.headers = headers
        if enabled is not None:
            server.enabled = enabled
        await self.session.flush()
        return server

    async def update_status(
        self,
        server_id: UUID,
        *,
        status: str,
        status_detail: str | None = None,
        tool_count: int | None = None,
    ) -> None:
        """Update connection status after a discovery attempt."""
        values: dict = {"status": status, "status_detail": status_detail}
        if tool_count is not None:
            values["tool_count"] = tool_count
        await self.session.execute(
            update(McpServerConfig)
            .where(McpServerConfig.id == server_id)
            .values(**values)
        )
        await self.session.flush()

    async def delete_server(self, server_id: UUID) -> bool:
        """Delete a server and cascade-remove its ToolConfig rows."""
        result = await self.session.execute(
            delete(McpServerConfig).where(McpServerConfig.id == server_id)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def sync_tools(
        self,
        server: McpServerConfig,
        discovered_tools: list[dict],
    ) -> list[ToolConfig]:
        """Sync discovered MCP tools into ToolConfig rows for the agent.

        - New tools are inserted.
        - Removed tools are deleted.
        - Existing tools have their schema updated but user edits (description,
          enabled, position) are preserved.

        Returns the final list of MCP ToolConfig rows for this server.
        """
        from backend.tools.executors.mcp_bridge import mcp_tool_to_tool_def

        agent_id = server.agent_id

        # Load existing MCP tools for this server.
        result = await self.session.execute(
            select(ToolConfig).where(
                ToolConfig.agent_id == agent_id,
                ToolConfig.mcp_server_id == server.id,
                ToolConfig.source == "mcp",
            )
        )
        existing = {tc.tool_name: tc for tc in result.scalars().all()}

        # Convert discovered tools to our format.
        discovered_map: dict[str, dict] = {}
        for mcp_tool in discovered_tools:
            tool_def = mcp_tool_to_tool_def(server, mcp_tool)
            discovered_map[tool_def["name"]] = tool_def

        # Determine the next position (after all existing agent tools).
        pos_result = await self.session.execute(
            select(ToolConfig.position)
            .where(ToolConfig.agent_id == agent_id)
            .order_by(ToolConfig.position.desc())
            .limit(1)
        )
        max_pos = pos_result.scalar_one_or_none() or 0
        next_pos = max_pos + 1

        final_tools: list[ToolConfig] = []

        # Upsert discovered tools.
        for name, tool_def in discovered_map.items():
            if name in existing:
                tc = existing[name]
                # Update schema (structural) but keep user edits.
                tc.input_schema = tool_def["input_schema"]
                final_tools.append(tc)
            else:
                tc = ToolConfig(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    tool_name=name,
                    description=tool_def["description"],
                    detailed_description=f"MCP tool from '{server.name}' server.",
                    input_schema=tool_def["input_schema"],
                    allowed_roles=["*"],
                    enabled=True,
                    position=next_pos,
                    source="mcp",
                    mcp_server_id=server.id,
                )
                self.session.add(tc)
                final_tools.append(tc)
                next_pos += 1

        # Delete tools that no longer exist on the server.
        removed_names = set(existing.keys()) - set(discovered_map.keys())
        if removed_names:
            await self.session.execute(
                delete(ToolConfig).where(
                    ToolConfig.agent_id == agent_id,
                    ToolConfig.mcp_server_id == server.id,
                    ToolConfig.tool_name.in_(removed_names),
                )
            )

        # Update server tool count.
        server.tool_count = len(final_tools)
        await self.session.flush()
        return final_tools
