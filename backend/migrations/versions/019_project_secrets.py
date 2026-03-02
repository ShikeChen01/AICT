"""Phase 19: Project Secrets — per-project secret tokens for agent use.

Introduces:
- project_secrets table: project_id, name, encrypted_value, hint
- Unique constraint on (project_id, name)

Revision ID: 019_project_secrets
Revises: 018_agent_token_allocations
Create Date: 2026-03-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_project_secrets"
down_revision: str = "018_agent_token_allocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("hint", sa.String(10), nullable=True),
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
    op.create_index(
        "ix_project_secrets_project_id", "project_secrets", ["project_id"]
    )
    op.create_unique_constraint(
        "uq_project_secrets_project_name",
        "project_secrets",
        ["project_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_project_secrets_project_name", "project_secrets", type_="unique"
    )
    op.drop_index("ix_project_secrets_project_id", table_name="project_secrets")
    op.drop_table("project_secrets")
