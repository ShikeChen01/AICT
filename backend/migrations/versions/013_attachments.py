"""Phase 6: image attachments stored in Postgres (bytea).

Creates:
  attachments         — binary image blob, sha256 hash, mime type, size, uploader
  message_attachments — junction table: channel_message ↔ attachment (ordered by position)

Revision ID: 013_attachments
Revises: 012_rate_limits_cost_budget
Create Date: 2026-02-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_attachments"
down_revision: str | None = "012_rate_limits_cost_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attachments_project", "attachments", ["project_id", "created_at"]
    )

    op.create_table(
        "message_attachments",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["channel_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_msg_attachments_message", "message_attachments", ["message_id"]
    )
    op.create_index(
        "ix_msg_attachments_attachment", "message_attachments", ["attachment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_msg_attachments_attachment", table_name="message_attachments")
    op.drop_index("ix_msg_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")
    op.drop_index("ix_attachments_project", table_name="attachments")
    op.drop_table("attachments")
