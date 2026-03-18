"""v4-005: Add target_user_id to channel_messages, backfill, remove USER_AGENT_ID sentinel.

Adds the symmetric target_user_id FK so agent-to-user messages are explicit.
Backfills existing rows:
  - Rows where from_agent_id = '00000000-...' (sentinel) get from_agent_id=NULL
    (from_user_id should already be populated for most of these).
  - Rows where target_agent_id = '00000000-...' (sentinel) get target_agent_id=NULL.
  - Rows where target_agent_id IS NULL, from_agent_id IS NOT NULL, broadcast=false
    (agent→user) attempt to set target_user_id from the project owner.

Revision ID: 005_add_target_user_id_remove_sentinel
Revises: 004_v4_grand_vm_columns
Create Date: 2026-03-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_add_target_user_id_remove_sentinel"
down_revision: str = "004_v4_grand_vm_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SENTINEL = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # 1. Add target_user_id column
    op.add_column(
        "channel_messages",
        sa.Column(
            "target_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Backfill: clear sentinel from from_agent_id
    op.execute(
        sa.text(
            "UPDATE channel_messages SET from_agent_id = NULL "
            "WHERE from_agent_id = :sentinel"
        ).bindparams(sentinel=_SENTINEL)
    )

    # 3. Backfill: clear sentinel from target_agent_id
    op.execute(
        sa.text(
            "UPDATE channel_messages SET target_agent_id = NULL "
            "WHERE target_agent_id = :sentinel"
        ).bindparams(sentinel=_SENTINEL)
    )

    # 4. Backfill target_user_id for agent→user messages using project owner.
    #    These are rows where: from_agent_id IS NOT NULL, target_agent_id IS NULL,
    #    broadcast=false, and target_user_id IS still NULL.
    op.execute(
        sa.text("""
            UPDATE channel_messages cm
            SET target_user_id = p.owner_id
            FROM projects p
            WHERE cm.project_id = p.id
              AND cm.from_agent_id IS NOT NULL
              AND cm.target_agent_id IS NULL
              AND cm.target_user_id IS NULL
              AND cm.broadcast = false
        """)
    )


def downgrade() -> None:
    # Restore sentinel values for agent→user and user→agent rows
    op.execute(
        sa.text(
            "UPDATE channel_messages "
            "SET target_agent_id = :sentinel "
            "WHERE target_user_id IS NOT NULL AND target_agent_id IS NULL"
        ).bindparams(sentinel=_SENTINEL)
    )
    op.execute(
        sa.text(
            "UPDATE channel_messages "
            "SET from_agent_id = :sentinel "
            "WHERE from_user_id IS NOT NULL AND from_agent_id IS NULL"
        ).bindparams(sentinel=_SENTINEL)
    )
    op.drop_column("channel_messages", "target_user_id")
