"""Phase 17: Tool Configs — per-agent customizable tool definitions.

Introduces:
- tool_configs table: per-agent and per-template tool configuration
  (description, detailed_description, input_schema, allowed_roles, enabled, position)

Data migration:
- Seeds tool_configs rows for all existing agents from tool_descriptions.json,
  filtered by agent role.

Revision ID: 017_tool_configs
Revises: 016_document_versioning
Create Date: 2026-03-01
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "017_tool_configs"
down_revision: str = "016_document_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOOLS_JSON = Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json"


def _normalize_detailed(raw) -> str:
    if isinstance(raw, list):
        return "\n".join(raw)
    return str(raw) if raw else ""


def _tools_for_role(agent_role: str) -> list[dict]:
    raw = json.loads(_TOOLS_JSON.read_text(encoding="utf-8"))
    result = []
    for t in raw:
        allowed = t.get("allowed_roles", ["*"])
        if "*" in allowed or agent_role in allowed:
            result.append(t)
    return result


def upgrade() -> None:
    # Create tool_configs table
    op.create_table(
        "tool_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detailed_description", sa.Text(), nullable=True),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("allowed_roles", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_configs_agent", "tool_configs", ["agent_id", "position"])
    op.create_index("ix_tool_configs_template", "tool_configs", ["template_id", "position"])

    # Seed tool_configs for all existing agents
    conn = op.get_bind()

    # Get all agents with their role
    agents = conn.execute(
        sa.text("SELECT id, role FROM agents")
    ).fetchall()

    rows = []
    for agent_row in agents:
        agent_id = agent_row[0]
        agent_role = agent_row[1] or "engineer"
        tools = _tools_for_role(agent_role)
        for position, t in enumerate(tools):
            rows.append({
                "id": str(uuid.uuid4()),
                "agent_id": str(agent_id),
                "template_id": None,
                "tool_name": t["name"],
                "description": t["description"],
                "detailed_description": _normalize_detailed(t.get("detailed_description", "")),
                "input_schema": json.dumps(t["input_schema"]),
                "allowed_roles": json.dumps(t.get("allowed_roles", ["*"])),
                "enabled": True,
                "position": position,
            })

    if rows:
        conn.execute(
            sa.text(
                "INSERT INTO tool_configs "
                "(id, agent_id, template_id, tool_name, description, detailed_description, "
                "input_schema, allowed_roles, enabled, position) "
                "VALUES (:id, :agent_id, :template_id, :tool_name, :description, "
                ":detailed_description, CAST(:input_schema AS jsonb), CAST(:allowed_roles AS jsonb), "
                ":enabled, :position)"
            ),
            rows,
        )


def downgrade() -> None:
    op.drop_index("ix_tool_configs_template", table_name="tool_configs")
    op.drop_index("ix_tool_configs_agent", table_name="tool_configs")
    op.drop_table("tool_configs")
