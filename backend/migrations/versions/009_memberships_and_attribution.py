"""Phase 2: repository_memberships table + channel_messages.from_user_id.

repository_memberships: tracks who has access to which project and with what role.
channel_messages.from_user_id: records the authenticated user who sent a message (when
sent from the REST API), enabling per-user attribution in the activity feed.

Data migration: for every repository with owner_id set, insert an 'owner' membership row
so existing projects continue to work after the access-check refactor.

Revision ID: 009_memberships_attribution
Revises: 008_add_agent_tier
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "009_memberships_attribution"
down_revision: str | None = "008_add_agent_tier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. repository_memberships
    op.create_table(
        "repository_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_repo_memberships_repo_user",
        "repository_memberships",
        ["repository_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "ix_repo_memberships_user",
        "repository_memberships",
        ["user_id"],
    )

    # 2. Backfill: owners of existing repositories get an 'owner' membership row
    op.execute(
        """
        INSERT INTO repository_memberships (id, repository_id, user_id, role, created_at)
        SELECT gen_random_uuid(), id, owner_id, 'owner', NOW()
        FROM repositories
        WHERE owner_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # 3. channel_messages.from_user_id (nullable FK to users; NULL = agent or system)
    op.add_column(
        "channel_messages",
        sa.Column("from_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_channel_messages_from_user",
        "channel_messages",
        ["from_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_messages_from_user", table_name="channel_messages")
    op.drop_column("channel_messages", "from_user_id")
    op.drop_index("ix_repo_memberships_user", table_name="repository_memberships")
    op.drop_index("ix_repo_memberships_repo_user", table_name="repository_memberships")
    op.drop_table("repository_memberships")
