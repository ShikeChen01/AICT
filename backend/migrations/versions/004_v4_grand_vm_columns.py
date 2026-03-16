"""v4-004: Add Grand-VM columns (unit_type on sandboxes, requires_desktop on sandbox_configs).

Adds the v4 dual-backend columns needed for the Grand-VM pivot:
  - sandboxes.unit_type: "headless" (default) or "desktop"
  - sandbox_configs.requires_desktop: whether this config requests a QEMU sub-VM

Revision ID: 004_v4_grand_vm_columns
Revises: 003_fix_duplicate_prompt_blocks
Create Date: 2026-03-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_v4_grand_vm_columns"
down_revision: str = "003_fix_duplicate_prompt_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # sandboxes.unit_type — defaults to "headless" for all existing rows
    op.add_column(
        "sandboxes",
        sa.Column(
            "unit_type",
            sa.String(20),
            nullable=False,
            server_default="headless",
        ),
    )

    # sandbox_configs.requires_desktop — defaults to False for all existing rows
    op.add_column(
        "sandbox_configs",
        sa.Column(
            "requires_desktop",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sandbox_configs", "requires_desktop")
    op.drop_column("sandboxes", "unit_type")
