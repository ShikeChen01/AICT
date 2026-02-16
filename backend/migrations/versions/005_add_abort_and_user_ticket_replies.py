"""Add abort fields to tasks and user replies to ticket_messages.

Revision ID: 005_abort_user_ticket_replies
Revises: 004_add_users_and_repositories
Create Date: 2026-02-16

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic. (max 32 chars for version_num)
revision = "005_abort_user_ticket_replies"
down_revision = "004_add_users_and_repositories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Task: add abort_reason, abort_documentation, aborted_by_id
    op.add_column("tasks", sa.Column("abort_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("abort_documentation", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("aborted_by_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_tasks_aborted_by_id_agents",
        "tasks",
        "agents",
        ["aborted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # TicketMessage: make from_agent_id nullable, add from_user_id
    op.alter_column(
        "ticket_messages",
        "from_agent_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column("ticket_messages", sa.Column("from_user_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_ticket_messages_from_user_id_users",
        "ticket_messages",
        "users",
        ["from_user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ticket_messages_from_user_id_users", "ticket_messages", type_="foreignkey")
    op.drop_column("ticket_messages", "from_user_id")
    op.alter_column(
        "ticket_messages",
        "from_agent_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_constraint("fk_tasks_aborted_by_id_agents", "tasks", type_="foreignkey")
    op.drop_column("tasks", "aborted_by_id")
    op.drop_column("tasks", "abort_documentation")
    op.drop_column("tasks", "abort_reason")
