"""Phase 4: llm_usage_events table + project_settings.daily_token_budget.

llm_usage_events: one row per LLM API call. Records provider, model, token counts,
timestamps, and context IDs for cost attribution and budget enforcement.

project_settings.daily_token_budget: if set (> 0), the agent loop aborts a session
when the project has exceeded this many tokens today (UTC).

Revision ID: 011_llm_usage_events
Revises: 010_project_settings_overrides
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "011_llm_usage_events"
down_revision: str | None = "010_project_settings_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_usage_project_time", "llm_usage_events", ["project_id", "created_at"])
    op.create_index("ix_llm_usage_agent", "llm_usage_events", ["agent_id"])
    op.create_index("ix_llm_usage_session", "llm_usage_events", ["session_id"])

    # Budget column on project_settings
    op.add_column(
        "project_settings",
        sa.Column(
            "daily_token_budget",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Max tokens per day (UTC) across all agents. 0 = unlimited.",
        ),
    )


def downgrade() -> None:
    op.drop_column("project_settings", "daily_token_budget")
    op.drop_index("ix_llm_usage_session", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_agent", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_project_time", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
