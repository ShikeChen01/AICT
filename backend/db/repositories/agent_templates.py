"""Repository for agent templates and prompt block configs."""

from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

import hashlib

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, AgentTemplate, PromptBlockConfig, ToolConfig
from backend.db.repositories.base import BaseRepository
from backend.llm.model_resolver import infer_provider

_BLOCKS_DIR = Path(__file__).parent.parent.parent / "prompts" / "blocks"

_THINKING_STAGE_CONTENT = (
    "## Thinking Phase\n\n"
    "You are in the thinking phase. Your ONLY job right now is to plan — do NOT execute any actions yet.\n\n"
    "Steps:\n"
    "1. Analyze the task and incoming messages carefully.\n"
    "2. Think through your approach: what needs to be done, in what order, what could go wrong.\n"
    "3. Break it down into a concrete, step-by-step plan.\n"
    "4. Save your detailed plan to memory using update_memory (under 'Active Task').\n"
    "5. When your plan is complete and saved, call thinking_done to begin execution.\n\n"
    "Available tools in this phase: update_memory, read_messages, read_history, thinking_done.\n"
    "Do NOT call any other tools. Do NOT start implementing."
)

_EXECUTION_STAGE_CONTENT = (
    "## Execution Phase\n\n"
    "You are in the execution phase. Your thinking plan is saved in your working memory.\n\n"
    "Steps:\n"
    "1. Read your plan from memory (it is in your current context under 'Active Task').\n"
    "2. Execute the plan step by step — build, verify each step before moving to the next.\n"
    "3. If you discover issues, update your plan in memory and adapt.\n"
    "4. When all steps are complete, call END.\n\n"
    "Your full tool set is now available. Build and verify systematically."
)

# (block_key, filename_or_None, position, enabled)
_COMMON_BLOCK_DEFS: list[tuple[str, str | None, int, bool]] = [
    ("rules",                  "rules.md",                  0,  True),
    ("history_rules",          "history_rules.md",          1,  True),
    ("incoming_message_rules", "incoming_message_rules.md", 2,  True),
    ("tool_result_rules",      "tool_result_rules.md",      3,  True),
    # tool_io at position 4 — role-specific, built separately
    # thinking injected at runtime
    ("memory",                 "memory_template.md",        6,  True),
    # identity at position 7 — role-specific, built separately
    ("loopback",               "loopback.md",               8,  True),
    ("end_solo_warning",       "end_solo_warning.md",       9,  True),
    ("summarization",          "summarization.md",          10, True),
    ("summarization_memory",   "summarization_memory.md",   10, True),
    ("summarization_history",  "summarization_history.md",  10, True),
    ("thinking_stage",         None,                        11, True),
    ("execution_stage",        None,                        12, True),
]

_ROLE_TOOL_IO: dict[str, str] = {
    "manager": "tool_io_manager.md",
    "cto":     "tool_io_cto.md",
    "worker":  "tool_io_engineer.md",
}

_ROLE_IDENTITY: dict[str, str] = {
    "manager": "identity_manager.md",
    "cto":     "identity_cto.md",
    "worker":  "identity_engineer.md",
}

_DEFAULT_MODELS: dict[str, str] = {
    "manager": "claude-sonnet-4-6",
    "cto":     "claude-opus-4-6",
    "worker":  "gpt-5.2",
}


def _read_block_file(filename: str) -> str:
    path = _BLOCKS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[Block file {filename} not found]"


def _build_block_defs_for_role(base_role: str) -> list[dict]:
    """Return list of block dicts for seeding a template or agent."""
    rows = []
    for block_key, filename, position, enabled in _COMMON_BLOCK_DEFS:
        if filename is not None:
            content = _read_block_file(filename)
        elif block_key == "thinking_stage":
            content = _THINKING_STAGE_CONTENT
        elif block_key == "execution_stage":
            content = _EXECUTION_STAGE_CONTENT
        else:
            content = ""
        rows.append({"block_key": block_key, "content": content, "position": position, "enabled": enabled})

    # tool_io: base + role-specific combined
    tool_io_base = _read_block_file("tool_io_base.md")
    tool_io_role_file = _ROLE_TOOL_IO.get(base_role)
    tool_io_role = _read_block_file(tool_io_role_file) if tool_io_role_file else ""
    rows.append({
        "block_key": "tool_io",
        "content": (tool_io_base + "\n" + tool_io_role).strip(),
        "position": 4,
        "enabled": True,
    })

    # identity: role-specific
    identity_file = _ROLE_IDENTITY.get(base_role)
    identity_content = _read_block_file(identity_file) if identity_file else "You are an agent on this project."
    rows.append({"block_key": "identity", "content": identity_content, "position": 7, "enabled": True})

    # secrets: per-project tokens (disabled by default; enable in Prompt Builder to inject {project_secrets})
    rows.append({
        "block_key": "secrets",
        "content": (
            "## Project secrets\n\n"
            "The following key-value pairs are configured for this project. Use them only when needed; "
            "do not echo or repeat them in channel messages.\n\n{project_secrets}"
        ),
        "position": 5,
        "enabled": False,
    })

    return rows


class AgentTemplateRepository(BaseRepository[AgentTemplate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AgentTemplate, session)

    async def list_by_project(self, project_id: UUID) -> list[AgentTemplate]:
        result = await self.session.execute(
            select(AgentTemplate)
            .where(AgentTemplate.project_id == project_id)
            .order_by(AgentTemplate.created_at)
        )
        return list(result.scalars().all())

    async def get_by_project_and_role(self, project_id: UUID, base_role: str) -> AgentTemplate | None:
        result = await self.session.execute(
            select(AgentTemplate).where(
                AgentTemplate.project_id == project_id,
                AgentTemplate.base_role == base_role,
                AgentTemplate.is_system_default == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def create_with_blocks(
        self,
        project_id: UUID,
        name: str,
        base_role: str,
        model: str,
        provider: str | None = None,
        thinking_enabled: bool = False,
        is_system_default: bool = False,
        description: str | None = None,
        sandbox_template: str | None = None,
        knowledge_sources: dict | list | None = None,
        trigger_config: dict | None = None,
        cost_limits: dict | None = None,
    ) -> AgentTemplate:
        """Create a template (agent design) and seed its prompt block configs."""
        if not provider:
            provider = infer_provider(model)

        template = AgentTemplate(
            id=uuid.uuid4(),
            project_id=project_id,
            name=name,
            description=description,
            base_role=base_role,
            model=model,
            provider=provider,
            thinking_enabled=thinking_enabled,
            sandbox_template=sandbox_template,
            knowledge_sources=knowledge_sources,
            trigger_config=trigger_config,
            cost_limits=cost_limits,
            is_system_default=is_system_default,
        )
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)

        # Seed blocks from .md files
        block_defs = _build_block_defs_for_role(base_role)
        for bd in block_defs:
            block = PromptBlockConfig(
                id=uuid.uuid4(),
                template_id=template.id,
                agent_id=None,
                block_key=bd["block_key"],
                content=bd["content"],
                position=bd["position"],
                enabled=bd["enabled"],
            )
            self.session.add(block)
        await self.session.flush()
        return template

    async def ensure_system_defaults(self, project_id: UUID) -> dict[str, AgentTemplate]:
        """Ensure system default templates exist for a project. Returns {base_role: template}.

        Uses a PostgreSQL advisory lock keyed on the project_id to prevent
        concurrent callers from creating duplicate system-default templates.
        Falls back to a no-op on non-PostgreSQL dialects (e.g. SQLite in tests).
        """
        dialect = self.session.bind.dialect.name if self.session.bind else ""
        if dialect == "postgresql":
            lock_key = int(hashlib.md5(project_id.bytes).hexdigest()[:15], 16)
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

        existing = await self.list_by_project(project_id)
        existing_defaults = {t.base_role: t for t in existing if t.is_system_default}

        defaults_config = [
            ("manager", "Manager", _DEFAULT_MODELS["manager"]),
            ("cto",     "CTO",     _DEFAULT_MODELS["cto"]),
            ("worker",  "Engineer", _DEFAULT_MODELS["worker"]),
        ]

        result: dict[str, AgentTemplate] = dict(existing_defaults)
        for base_role, name, model in defaults_config:
            if base_role not in existing_defaults:
                template = await self.create_with_blocks(
                    project_id=project_id,
                    name=name,
                    base_role=base_role,
                    model=model,
                    is_system_default=True,
                )
                result[base_role] = template

        return result


class PromptBlockConfigRepository(BaseRepository[PromptBlockConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PromptBlockConfig, session)

    async def list_for_agent(self, agent_id: UUID) -> list[PromptBlockConfig]:
        """Return all block configs for an agent, ordered by position."""
        result = await self.session.execute(
            select(PromptBlockConfig)
            .where(PromptBlockConfig.agent_id == agent_id)
            .order_by(PromptBlockConfig.position)
        )
        return list(result.scalars().all())

    async def list_for_template(self, template_id: UUID) -> list[PromptBlockConfig]:
        """Return all block configs for a template, ordered by position."""
        result = await self.session.execute(
            select(PromptBlockConfig)
            .where(PromptBlockConfig.template_id == template_id)
            .order_by(PromptBlockConfig.position)
        )
        return list(result.scalars().all())

    async def copy_template_blocks_to_agent(self, template_id: UUID, agent_id: UUID) -> list[PromptBlockConfig]:
        """Copy all template-level blocks to agent-level blocks (idempotent).

        Skips any block_key that already exists for this agent to avoid
        duplicates when called concurrently or repeatedly.
        """
        template_blocks = await self.list_for_template(template_id)
        existing = await self.list_for_agent(agent_id)
        existing_keys = {b.block_key for b in existing}

        agent_blocks = list(existing)
        for tb in template_blocks:
            if tb.block_key in existing_keys:
                continue
            block = PromptBlockConfig(
                id=uuid.uuid4(),
                template_id=None,
                agent_id=agent_id,
                block_key=tb.block_key,
                content=tb.content,
                position=tb.position,
                enabled=tb.enabled,
            )
            self.session.add(block)
            agent_blocks.append(block)
            existing_keys.add(tb.block_key)
        await self.session.flush()
        return agent_blocks

    async def bulk_replace_agent_blocks(
        self, agent_id: UUID, blocks: list[dict]
    ) -> list[PromptBlockConfig]:
        """Replace all agent-level blocks with the provided list.

        Each dict in blocks: {block_key, content, position, enabled}.
        """
        await self.session.execute(
            delete(PromptBlockConfig).where(PromptBlockConfig.agent_id == agent_id)
        )
        new_blocks = []
        for bd in blocks:
            block = PromptBlockConfig(
                id=uuid.uuid4(),
                template_id=None,
                agent_id=agent_id,
                block_key=bd["block_key"],
                content=bd.get("content", ""),
                position=bd.get("position", 0),
                enabled=bd.get("enabled", True),
            )
            self.session.add(block)
            new_blocks.append(block)
        await self.session.flush()
        return new_blocks

    async def bulk_replace_template_blocks(
        self, template_id: UUID, blocks: list[dict]
    ) -> list[PromptBlockConfig]:
        """Replace all template-level blocks with the provided list."""
        await self.session.execute(
            delete(PromptBlockConfig).where(PromptBlockConfig.template_id == template_id)
        )
        new_blocks = []
        for bd in blocks:
            block = PromptBlockConfig(
                id=uuid.uuid4(),
                template_id=template_id,
                agent_id=None,
                block_key=bd["block_key"],
                content=bd.get("content", ""),
                position=bd.get("position", 0),
                enabled=bd.get("enabled", True),
            )
            self.session.add(block)
            new_blocks.append(block)
        await self.session.flush()
        return new_blocks

    async def reset_agent_block_to_default(
        self, agent_id: UUID, block_id: UUID, base_role: str
    ) -> PromptBlockConfig | None:
        """Reset a single agent block's content to the .md file default."""
        result = await self.session.execute(
            select(PromptBlockConfig).where(
                PromptBlockConfig.id == block_id,
                PromptBlockConfig.agent_id == agent_id,
            )
        )
        block = result.scalar_one_or_none()
        if not block:
            return None

        # Rebuild defaults to find the right content
        defaults = {bd["block_key"]: bd["content"] for bd in _build_block_defs_for_role(base_role)}
        default_content = defaults.get(block.block_key, "")
        if default_content:
            block.content = default_content
            await self.session.flush()
        return block

    async def ensure_agent_blocks(self, agent_id: UUID, role: str) -> list[PromptBlockConfig]:
        """Return existing blocks for an agent, auto-seeding defaults if empty.

        Covers agents created before the prompt-block system was introduced.
        """
        blocks = await self.list_for_agent(agent_id)
        if blocks:
            return blocks
        role_map = {"manager": "manager", "cto": "cto", "engineer": "worker"}
        base_role = role_map.get(role, "worker")
        return await self.bulk_replace_agent_blocks(agent_id, _build_block_defs_for_role(base_role))

    @staticmethod
    def get_default_blocks_for_role(base_role: str) -> list[dict]:
        """Return the codebase default blocks for a given base_role (for the API)."""
        return _build_block_defs_for_role(base_role)
