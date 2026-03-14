"""v3.1-003: Fix duplicate prompt blocks and add unique constraint.

Cleans up duplicate prompt_block_configs rows caused by a race condition
where list_agent_blocks and get_prompt_meta both called ensure_agent_blocks
concurrently, and adds a unique constraint to prevent future duplicates.

Revision ID: 003_fix_duplicate_prompt_blocks
Revises: 002_sandbox_user_ownership
Create Date: 2026-03-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_fix_duplicate_prompt_blocks"
down_revision: str = "002_sandbox_user_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Step 1: Remove duplicate prompt blocks ────────────────────────
    # Keep the oldest row (MIN(id)) per (agent_id, block_key) group.
    # Delete all other duplicates.
    conn = op.get_bind()

    # Check dialect — SQLite (tests) doesn't support CTEs the same way
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("""
            DELETE FROM prompt_block_configs
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY agent_id, block_key
                               ORDER BY created_at ASC, id ASC
                           ) AS rn
                    FROM prompt_block_configs
                    WHERE agent_id IS NOT NULL
                ) ranked
                WHERE rn > 1
            )
        """))

        # Also deduplicate template-level blocks
        conn.execute(sa.text("""
            DELETE FROM prompt_block_configs
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY template_id, block_key
                               ORDER BY created_at ASC, id ASC
                           ) AS rn
                    FROM prompt_block_configs
                    WHERE template_id IS NOT NULL
                ) ranked
                WHERE rn > 1
            )
        """))

    # ── Step 2: Add unique constraints ────────────────────────────────
    op.create_unique_constraint(
        "uq_prompt_block_configs_agent_key",
        "prompt_block_configs",
        ["agent_id", "block_key"],
    )
    op.create_unique_constraint(
        "uq_prompt_block_configs_template_key",
        "prompt_block_configs",
        ["template_id", "block_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_prompt_block_configs_template_key", "prompt_block_configs", type_="unique")
    op.drop_constraint("uq_prompt_block_configs_agent_key", "prompt_block_configs", type_="unique")
