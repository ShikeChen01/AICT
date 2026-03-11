"""Repository for ToolConfig — per-agent tool customization."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ToolConfig
from backend.db.repositories.base import BaseRepository

_TOOLS_JSON_PATH = Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json"


def _load_raw_tools() -> list[dict]:
    """Load raw tool definitions from tool_descriptions.json."""
    return json.loads(_TOOLS_JSON_PATH.read_text(encoding="utf-8"))


def _normalize_detailed_description(raw: str | list) -> str:
    if isinstance(raw, list):
        return "\n".join(raw)
    return str(raw) if raw else ""


def build_tool_defs_for_role(base_role: str) -> list[dict]:
    """Return tool defs that are applicable to the given base_role.

    base_role: 'manager', 'cto', 'worker'
    Filters by allowed_roles: includes tools with '*' or the matching role.
    """
    role_map = {"manager": "manager", "cto": "cto", "worker": "engineer"}
    agent_role = role_map.get(base_role, "engineer")

    raw = _load_raw_tools()
    result = []
    for t in raw:
        allowed = t.get("allowed_roles", ["*"])
        if "*" in allowed or agent_role in allowed:
            result.append(t)
    return result


class ToolConfigRepository(BaseRepository[ToolConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ToolConfig, session)

    async def list_for_agent(self, agent_id: UUID) -> list[ToolConfig]:
        """Return all tool configs for an agent, ordered by position."""
        result = await self.session.execute(
            select(ToolConfig)
            .where(ToolConfig.agent_id == agent_id)
            .order_by(ToolConfig.position)
        )
        return list(result.scalars().all())

    async def list_for_template(self, template_id: UUID) -> list[ToolConfig]:
        result = await self.session.execute(
            select(ToolConfig)
            .where(ToolConfig.template_id == template_id)
            .order_by(ToolConfig.position)
        )
        return list(result.scalars().all())

    async def get_by_agent_and_name(self, agent_id: UUID, tool_name: str) -> ToolConfig | None:
        result = await self.session.execute(
            select(ToolConfig).where(
                ToolConfig.agent_id == agent_id,
                ToolConfig.tool_name == tool_name,
            )
        )
        return result.scalar_one_or_none()

    async def seed_for_agent(self, agent_id: UUID, base_role: str) -> list[ToolConfig]:
        """Seed ToolConfig rows for an agent from tool_descriptions.json.

        Filtered by base_role. Idempotent: if rows exist, returns them unchanged.
        """
        existing = await self.list_for_agent(agent_id)
        if existing:
            return existing

        tool_defs = build_tool_defs_for_role(base_role)
        configs = []
        for position, t in enumerate(tool_defs):
            tc = ToolConfig(
                id=uuid.uuid4(),
                agent_id=agent_id,
                template_id=None,
                tool_name=t["name"],
                description=t["description"],
                detailed_description=_normalize_detailed_description(
                    t.get("detailed_description", "")
                ),
                input_schema=t["input_schema"],
                allowed_roles=t.get("allowed_roles", ["*"]),
                enabled=True,
                position=position,
            )
            self.session.add(tc)
            configs.append(tc)
        await self.session.flush()
        return configs

    async def _add_missing_defaults_for_agent(
        self,
        agent_id: UUID,
        base_role: str,
        existing: list[ToolConfig],
    ) -> list[ToolConfig]:
        """Backfill newly introduced default tools onto existing agents."""
        existing_names = {tc.tool_name for tc in existing}
        tool_defs = build_tool_defs_for_role(base_role)
        next_position = (max((tc.position for tc in existing), default=-1) + 1)

        added = False
        for t in tool_defs:
            if t["name"] in existing_names:
                continue
            tc = ToolConfig(
                id=uuid.uuid4(),
                agent_id=agent_id,
                template_id=None,
                tool_name=t["name"],
                description=t["description"],
                detailed_description=_normalize_detailed_description(
                    t.get("detailed_description", "")
                ),
                input_schema=t["input_schema"],
                allowed_roles=t.get("allowed_roles", ["*"]),
                enabled=True,
                position=next_position,
            )
            self.session.add(tc)
            existing.append(tc)
            existing_names.add(t["name"])
            next_position += 1
            added = True

        if added:
            await self.session.flush()
        return existing

    async def bulk_update_agent_tools(
        self,
        agent_id: UUID,
        updates: list[dict],
    ) -> list[ToolConfig]:
        """Bulk update description, detailed_description, enabled, position for each tool.

        Only editable fields are updated; tool_name, input_schema, allowed_roles are preserved.
        """
        existing = {tc.tool_name: tc for tc in await self.list_for_agent(agent_id)}
        for item in updates:
            tool_name = item.get("tool_name", "")
            tc = existing.get(tool_name)
            if tc is None:
                continue
            if "description" in item:
                tc.description = item["description"]
            if "detailed_description" in item:
                tc.detailed_description = item["detailed_description"]
            if "enabled" in item:
                tc.enabled = bool(item["enabled"])
            if "position" in item:
                tc.position = int(item["position"])
        await self.session.flush()
        return await self.list_for_agent(agent_id)

    async def reset_to_default(self, agent_id: UUID, tool_config_id: UUID) -> ToolConfig | None:
        """Reset a single tool config to its JSON-file defaults."""
        result = await self.session.execute(
            select(ToolConfig).where(
                ToolConfig.id == tool_config_id,
                ToolConfig.agent_id == agent_id,
            )
        )
        tc = result.scalar_one_or_none()
        if tc is None:
            return None

        raw = _load_raw_tools()
        raw_map = {t["name"]: t for t in raw}
        defaults = raw_map.get(tc.tool_name)
        if defaults:
            tc.description = defaults["description"]
            tc.detailed_description = _normalize_detailed_description(
                defaults.get("detailed_description", "")
            )
        await self.session.flush()
        return tc

    async def ensure_agent_tools(self, agent_id: UUID, base_role: str) -> list[ToolConfig]:
        """Return existing tool configs for agent, seeding defaults if missing."""
        existing = await self.list_for_agent(agent_id)
        if existing:
            return await self._add_missing_defaults_for_agent(agent_id, base_role, existing)
        return await self.seed_for_agent(agent_id, base_role)
