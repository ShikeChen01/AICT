"""Phase 15: Agent Templates and Prompt Block Configuration.

Introduces:
- agent_templates table: reusable agent configuration (replaces role+tier+model_overrides)
- prompt_block_configs table: per-template and per-agent prompt blocks (DB source of truth)
- agents.template_id, agents.provider, agents.thinking_enabled columns

Data migration:
- Creates system default templates (Manager, CTO, Engineer) for each project
- Seeds prompt_block_configs rows from .md files for each template
- Populates agent.provider by inferring from agent.model
- Links existing agents to templates by role

Revision ID: 015_agent_templates
Revises: 014_project_documents
Create Date: 2026-03-01
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "015_agent_templates"
down_revision: str | None = "014_project_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Block files location ──────────────────────────────────────────────────────

_BLOCKS_DIR = Path(__file__).parent.parent.parent / "prompts" / "blocks"


def _read_block(filename: str) -> str:
    path = _BLOCKS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[Block {filename} not found]"


# ── Prompt block definitions: (block_key, filename, position, enabled) ────────
# Position determines system prompt order. thinking_stage/execution_stage are
# stage-specific and will be filtered by PromptAssembly at runtime.

_COMMON_BLOCKS: list[tuple[str, str, int, bool]] = [
    ("rules",                   "rules.md",                   0,  True),
    ("history_rules",           "history_rules.md",           1,  True),
    ("incoming_message_rules",  "incoming_message_rules.md",  2,  True),
    ("tool_result_rules",       "tool_result_rules.md",       3,  True),
    # tool_io is role-specific (set per template below)
    # thinking (injected at runtime, not stored)
    ("memory",                  "memory_template.md",         6,  True),
    # identity is role-specific (set per template below)
    ("loopback",                "loopback.md",                8,  True),
    ("end_solo_warning",        "end_solo_warning.md",        9,  True),
    ("summarization",           "summarization.md",           10, True),
    ("thinking_stage",          None,                         11, True),
    ("execution_stage",         None,                         12, True),
]

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

_TOOL_IO_POSITION = 4
_IDENTITY_POSITION = 7

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

# ── Provider inference ────────────────────────────────────────────────────────

_OPENAI_O_RE = re.compile(r"^o\d")


def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "gemini" in m or "google" in m:
        return "google"
    if "kimi" in m or "moonshot" in m or m.startswith("k2") or m.startswith("moonshot-v1"):
        return "kimi"
    if "gpt" in m or "chatgpt" in m or "openai" in m or _OPENAI_O_RE.match(m):
        return "openai"
    return "anthropic"


# ── Default models (fallback if no project_settings.model_overrides) ─────────

_DEFAULT_MODELS: dict[str, str] = {
    "manager": "claude-sonnet-4-6",
    "cto":     "claude-opus-4-6",
    "worker":  "gpt-5.2",
}

# Maps agent role -> base_role on template
_ROLE_TO_BASE_ROLE: dict[str, str] = {
    "manager":  "manager",
    "cto":      "cto",
    "engineer": "worker",
}


def _build_blocks_for_base_role(base_role: str) -> list[dict]:
    """Build the list of block dicts to insert for a template of the given base_role."""
    rows = []
    # common blocks
    for block_key, filename, position, enabled in _COMMON_BLOCKS:
        if filename is not None:
            content = _read_block(filename)
        elif block_key == "thinking_stage":
            content = _THINKING_STAGE_CONTENT
        elif block_key == "execution_stage":
            content = _EXECUTION_STAGE_CONTENT
        else:
            content = ""
        rows.append({
            "block_key": block_key,
            "content": content,
            "position": position,
            "enabled": enabled,
        })

    # role-specific tool_io (base + role-specific combined)
    tool_io_base = _read_block("tool_io_base.md")
    tool_io_role_file = _ROLE_TOOL_IO.get(base_role)
    tool_io_role = _read_block(tool_io_role_file) if tool_io_role_file else ""
    tool_io_content = (tool_io_base + "\n" + tool_io_role).strip()
    rows.append({
        "block_key": "tool_io",
        "content": tool_io_content,
        "position": _TOOL_IO_POSITION,
        "enabled": True,
    })

    # role-specific identity
    identity_file = _ROLE_IDENTITY.get(base_role)
    identity_content = _read_block(identity_file) if identity_file else f"You are an agent on this project."
    rows.append({
        "block_key": "identity",
        "content": identity_content,
        "position": _IDENTITY_POSITION,
        "enabled": True,
    })

    return rows


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Create agent_templates table ──────────────────────────────────────
    op.create_table(
        "agent_templates",
        sa.Column(
            "id", sa.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_role", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("tool_access", sa.JSON, nullable=True),
        sa.Column("is_system_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_templates_project", "agent_templates", ["project_id"])

    # ── 2. Create prompt_block_configs table ──────────────────────────────────
    op.create_table(
        "prompt_block_configs",
        sa.Column(
            "id", sa.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "template_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "agent_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("block_key", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_prompt_block_configs_template", "prompt_block_configs", ["template_id", "position"])
    op.create_index("ix_prompt_block_configs_agent", "prompt_block_configs", ["agent_id", "position"])

    # ── 3. Add new columns to agents ──────────────────────────────────────────
    op.add_column("agents", sa.Column(
        "template_id", sa.UUID(as_uuid=True),
        sa.ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("agents", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("agents", sa.Column(
        "thinking_enabled", sa.Boolean, nullable=False, server_default="false",
    ))

    # ── 4. Data migration ─────────────────────────────────────────────────────

    # 4a. Fetch all projects
    projects = conn.execute(sa.text("SELECT id FROM repositories")).fetchall()

    # 4b. Fetch all project_settings for model_overrides
    settings_rows = conn.execute(
        sa.text("SELECT project_id, model_overrides FROM project_settings")
    ).fetchall()
    model_overrides_by_project: dict = {}
    for row in settings_rows:
        if row[1]:
            model_overrides_by_project[str(row[0])] = row[1]

    for project_row in projects:
        project_id = str(project_row[0])
        overrides = model_overrides_by_project.get(project_id, {})

        # Resolve models from overrides or defaults
        manager_model = overrides.get("manager") or _DEFAULT_MODELS["manager"]
        cto_model = overrides.get("cto") or _DEFAULT_MODELS["cto"]
        engineer_model = (
            overrides.get("engineer_intermediate")
            or overrides.get("engineer_junior")
            or _DEFAULT_MODELS["worker"]
        )

        role_models = {
            "manager": manager_model,
            "cto": cto_model,
            "worker": engineer_model,
        }
        role_names = {
            "manager": "Manager",
            "cto": "CTO",
            "worker": "Engineer",
        }

        # Create one template per base_role
        template_ids: dict[str, str] = {}
        for base_role in ("manager", "cto", "worker"):
            model = role_models[base_role]
            provider = _infer_provider(model)
            template_id = str(uuid.uuid4())
            template_ids[base_role] = template_id

            conn.execute(sa.text("""
                INSERT INTO agent_templates
                    (id, project_id, name, base_role, model, provider,
                     thinking_enabled, is_system_default, created_at, updated_at)
                VALUES
                    (:id, :project_id, :name, :base_role, :model, :provider,
                     false, true, now(), now())
            """), {
                "id": template_id,
                "project_id": project_id,
                "name": role_names[base_role],
                "base_role": base_role,
                "model": model,
                "provider": provider,
            })

            # Seed prompt block configs for this template
            blocks = _build_blocks_for_base_role(base_role)
            for block in blocks:
                conn.execute(sa.text("""
                    INSERT INTO prompt_block_configs
                        (id, template_id, agent_id, block_key, content, position, enabled, created_at, updated_at)
                    VALUES
                        (:id, :template_id, NULL, :block_key, :content, :position, :enabled, now(), now())
                """), {
                    "id": str(uuid.uuid4()),
                    "template_id": template_id,
                    "block_key": block["block_key"],
                    "content": block["content"],
                    "position": block["position"],
                    "enabled": block["enabled"],
                })

    # 4c. Fetch all existing agents and link them to templates
    agents = conn.execute(
        sa.text("SELECT id, project_id, role, model FROM agents")
    ).fetchall()

    # Build a lookup: project_id -> {base_role -> template_id}
    template_lookup: dict[str, dict[str, str]] = {}
    tmpl_rows = conn.execute(
        sa.text("SELECT id, project_id, base_role FROM agent_templates")
    ).fetchall()
    for row in tmpl_rows:
        pid = str(row[1])
        if pid not in template_lookup:
            template_lookup[pid] = {}
        template_lookup[pid][row[2]] = str(row[0])

    for agent_row in agents:
        agent_id = str(agent_row[0])
        project_id = str(agent_row[1])
        role = agent_row[2]
        model = agent_row[3] or _DEFAULT_MODELS.get(_ROLE_TO_BASE_ROLE.get(role, "worker"), "claude-sonnet-4-6")

        base_role = _ROLE_TO_BASE_ROLE.get(role, "worker")
        provider = _infer_provider(model)
        template_id = template_lookup.get(project_id, {}).get(base_role)

        conn.execute(sa.text("""
            UPDATE agents
            SET provider = :provider,
                template_id = :template_id
            WHERE id = :agent_id
        """), {
            "provider": provider,
            "template_id": template_id,
            "agent_id": agent_id,
        })

        # Copy template blocks to agent-level blocks
        if template_id:
            tmpl_blocks = conn.execute(sa.text("""
                SELECT block_key, content, position, enabled
                FROM prompt_block_configs
                WHERE template_id = :template_id
            """), {"template_id": template_id}).fetchall()

            for block in tmpl_blocks:
                conn.execute(sa.text("""
                    INSERT INTO prompt_block_configs
                        (id, template_id, agent_id, block_key, content, position, enabled, created_at, updated_at)
                    VALUES
                        (:id, NULL, :agent_id, :block_key, :content, :position, :enabled, now(), now())
                """), {
                    "id": str(uuid.uuid4()),
                    "agent_id": agent_id,
                    "block_key": block[0],
                    "content": block[1],
                    "position": block[2],
                    "enabled": block[3],
                })

    # 4d. Apply prompt_overrides: append existing override text to agent identity blocks
    prompt_override_rows = conn.execute(
        sa.text("SELECT project_id, prompt_overrides FROM project_settings WHERE prompt_overrides IS NOT NULL")
    ).fetchall()

    for row in prompt_override_rows:
        project_id = str(row[0])
        prompt_overrides = row[1]
        if not prompt_overrides:
            continue

        # role -> override text mapping from old system
        role_override_map = {
            "manager": prompt_overrides.get("manager", ""),
            "cto": prompt_overrides.get("cto", ""),
            "engineer": prompt_overrides.get("engineer", ""),
        }

        for agent_role, override_text in role_override_map.items():
            if not override_text:
                continue
            # Append to identity block of agents in this project with this role
            conn.execute(sa.text("""
                UPDATE prompt_block_configs pbc
                SET content = pbc.content || :override_text,
                    updated_at = now()
                FROM agents a
                WHERE pbc.agent_id = a.id
                  AND a.project_id = :project_id
                  AND a.role = :agent_role
                  AND pbc.block_key = 'identity'
            """), {
                "project_id": project_id,
                "agent_role": agent_role,
                "override_text": "\n\n## Project-specific instructions\n\n" + override_text,
            })


def downgrade() -> None:
    op.drop_column("agents", "thinking_enabled")
    op.drop_column("agents", "provider")
    op.drop_column("agents", "template_id")

    op.drop_index("ix_prompt_block_configs_agent", table_name="prompt_block_configs")
    op.drop_index("ix_prompt_block_configs_template", table_name="prompt_block_configs")
    op.drop_table("prompt_block_configs")

    op.drop_index("ix_agent_templates_project", table_name="agent_templates")
    op.drop_table("agent_templates")
