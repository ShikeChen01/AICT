"""Deduplicate prompt_block_configs and add unique constraints.

Race conditions in ensure_system_defaults() and copy_template_blocks_to_agent()
could create duplicate rows with the same (agent_id, block_key) or
(template_id, block_key). This migration removes duplicates (keeping the earliest
row) and adds partial unique indexes to prevent future duplicates.

Revision ID: 023
Revises: 022
"""

from alembic import op

revision = "023_dedup_prompt_blocks"
down_revision = "022_agent_designs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Deduplicate agent-level blocks ────────────────────────────────
    # Keep the row with the smallest created_at (earliest); delete later dups.
    op.execute("""
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
        );
    """)

    # ── 2. Deduplicate template-level blocks ─────────────────────────────
    op.execute("""
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
        );
    """)

    # ── 3. Add partial unique indexes (NULL-safe) ────────────────────────
    # Partial indexes: only apply where the FK column IS NOT NULL.
    op.execute("""
        CREATE UNIQUE INDEX uq_prompt_block_agent_key
        ON prompt_block_configs (agent_id, block_key)
        WHERE agent_id IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_prompt_block_template_key
        ON prompt_block_configs (template_id, block_key)
        WHERE template_id IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_prompt_block_template_key;")
    op.execute("DROP INDEX IF EXISTS uq_prompt_block_agent_key;")
