"""Deprecate OM: update agents with role 'om' to role 'cto' and display_name 'CTO'.

Revision ID: 007_deprecate_om_cto
Revises: 006_data_messaging
Create Date: 2026-02-18

Backend and frontend use CTO only; DB must never expose 'om'.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007_deprecate_om_cto"
down_revision: str | None = "006_data_messaging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Update any existing OM agents to CTO so backend never returns 'om'
    op.execute(
        """
        UPDATE agents
        SET role = 'cto', display_name = 'CTO'
        WHERE role = 'om'
        """
    )


def downgrade() -> None:
    # Revert CTO agents that were formerly OM (best-effort: only those named 'CTO')
    op.execute(
        """
        UPDATE agents
        SET role = 'om', display_name = 'Operations Manager'
        WHERE role = 'cto' AND display_name = 'CTO'
        """
    )
