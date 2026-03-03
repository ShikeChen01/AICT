"""Phase 20: Sandbox Configs — user-level sandbox configuration profiles.

Introduces:
- sandbox_configs table: user-owned setup profiles (setup script, description)
- sandbox_config_id FK on agents table to link an agent to a config

Users create sandbox configs (e.g. "Chrome + Slack + VS Code") with a setup
script that runs inside the container after creation.  Configs are user-level
so they can be reused across projects and agents.

Revision ID: 020_sandbox_configs
Revises: 019_project_secrets
Create Date: 2026-03-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_sandbox_configs"
down_revision: str = "019_project_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sandbox_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("setup_script", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_sandbox_configs_user_id", "sandbox_configs", ["user_id"])
    op.create_unique_constraint(
        "uq_sandbox_configs_user_name", "sandbox_configs", ["user_id", "name"]
    )

    # Link agents to sandbox configs
    op.add_column(
        "agents",
        sa.Column(
            "sandbox_config_id",
            sa.Uuid(),
            sa.ForeignKey("sandbox_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "sandbox_config_id")
    op.drop_constraint("uq_sandbox_configs_user_name", "sandbox_configs", type_="unique")
    op.drop_index("ix_sandbox_configs_user_id", table_name="sandbox_configs")
    op.drop_table("sandbox_configs")
