"""Add optional tier column on agents for model policy selection.

Revision ID: 008_add_agent_tier
Revises: 007_deprecate_om_cto
Create Date: 2026-02-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_add_agent_tier"
down_revision: str | None = "007_deprecate_om_cto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("tier", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "tier")
