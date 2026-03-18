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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("channel_messages")}

    if "target_user_id" not in column_names:
        op.add_column(
            "channel_messages",
            sa.Column(
                "target_user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    channel_messages = sa.table(
        "channel_messages",
        sa.column("project_id", sa.Uuid()),
        sa.column("from_agent_id", sa.Uuid()),
        sa.column("target_agent_id", sa.Uuid()),
        sa.column("from_user_id", sa.Uuid()),
        sa.column("target_user_id", sa.Uuid()),
        sa.column("broadcast", sa.Boolean()),
    )
    projects = sa.table(
        "projects",
        sa.column("id", sa.Uuid()),
        sa.column("owner_id", sa.Uuid()),
    )

    op.execute(
        channel_messages.update()
        .where(channel_messages.c.from_agent_id == sa.cast(_SENTINEL, sa.Uuid()))
        .values(from_agent_id=None)
    )

    op.execute(
        channel_messages.update()
        .where(channel_messages.c.target_agent_id == sa.cast(_SENTINEL, sa.Uuid()))
        .values(target_agent_id=None)
    )

    owner_subquery = (
        sa.select(projects.c.owner_id)
        .where(projects.c.id == channel_messages.c.project_id)
        .scalar_subquery()
    )
    op.execute(
        channel_messages.update()
        .where(channel_messages.c.from_agent_id.is_not(None))
        .where(channel_messages.c.target_agent_id.is_(None))
        .where(channel_messages.c.target_user_id.is_(None))
        .where(channel_messages.c.broadcast.is_(False))
        .values(target_user_id=owner_subquery)
    )


def downgrade() -> None:
    channel_messages = sa.table(
        "channel_messages",
        sa.column("from_agent_id", sa.Uuid()),
        sa.column("target_agent_id", sa.Uuid()),
        sa.column("from_user_id", sa.Uuid()),
        sa.column("target_user_id", sa.Uuid()),
    )

    op.execute(
        channel_messages.update()
        .where(channel_messages.c.target_user_id.is_not(None))
        .where(channel_messages.c.target_agent_id.is_(None))
        .values(target_agent_id=sa.cast(_SENTINEL, sa.Uuid()))
    )
    op.execute(
        channel_messages.update()
        .where(channel_messages.c.from_user_id.is_not(None))
        .where(channel_messages.c.from_agent_id.is_(None))
        .values(from_agent_id=sa.cast(_SENTINEL, sa.Uuid()))
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("channel_messages")}
    if "target_user_id" in column_names:
        op.drop_column("channel_messages", "target_user_id")
