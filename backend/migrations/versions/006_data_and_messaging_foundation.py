"""Data and messaging foundation: new tables, agents/tasks changes, drop deprecated.

Revision ID: 006_data_messaging
Revises: 005_abort_user_ticket_replies
Create Date: 2026-02-18

Per docs/db.md: add project_settings, channel_messages, agent_messages, agent_sessions;
add agents.memory, drop agents.priority; drop tasks abort fields; migrate chat_messages
then drop chat_messages, tickets, ticket_messages, engineer_jobs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "006_data_messaging"
down_revision: str | None = "005_abort_user_ticket_replies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_AGENT_ID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # 1. Add project_settings table
    op.create_table(
        "project_settings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("max_engineers", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("persistent_sandbox_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_project_settings_project_id"),
    )
    op.create_index("ix_project_settings_project_id", "project_settings", ["project_id"], unique=True)

    # 2. Add memory column to agents
    op.add_column("agents", sa.Column("memory", JSONB(), nullable=True))

    # 3. Create channel_messages (no FK on from_agent_id/target_agent_id — user = reserved UUID)
    op.create_table(
        "channel_messages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("broadcast", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_target_status", "channel_messages", ["target_agent_id", "status", "created_at"])
    op.create_index("ix_channel_project", "channel_messages", ["project_id", "created_at"])

    # 4. Create agent_sessions
    op.create_table(
        "agent_sessions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trigger_message_id"], ["channel_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_sessions_agent", "agent_sessions", ["agent_id", "started_at"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])

    # 5. Create agent_messages
    op.create_table(
        "agent_messages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_input", JSONB(), nullable=True),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("loop_iteration", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_messages_agent_time", "agent_messages", ["agent_id", "created_at"])
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id", "loop_iteration"])

    # 6. Migrate chat_messages -> channel_messages (user = USER_AGENT_ID, gm/manager -> manager agent)
    op.execute(
        sa.text(
            """
        INSERT INTO channel_messages (id, project_id, from_agent_id, target_agent_id, content, message_type, status, broadcast, created_at)
        SELECT
            cm.id,
            cm.project_id,
            CASE WHEN cm.role = 'user' THEN '00000000-0000-0000-0000-000000000000'::uuid ELSE (SELECT id FROM agents a WHERE a.project_id = cm.project_id AND a.role IN ('gm','manager') LIMIT 1) END,
            CASE WHEN cm.role = 'user' THEN (SELECT id FROM agents a WHERE a.project_id = cm.project_id AND a.role IN ('gm','manager') LIMIT 1) ELSE '00000000-0000-0000-0000-000000000000'::uuid END,
            cm.content,
            'normal',
            'received',
            false,
            cm.created_at
        FROM chat_messages cm
        """
        )
    )

    # 7. Drop chat_messages
    op.drop_table("chat_messages")

    # 8. Drop ticket_messages then tickets
    op.drop_table("ticket_messages")
    op.drop_table("tickets")

    # 9. Drop engineer_jobs
    op.drop_table("engineer_jobs")

    # 10. Remove abort fields from tasks
    op.drop_constraint("fk_tasks_aborted_by_id_agents", "tasks", type_="foreignkey")
    op.drop_column("tasks", "aborted_by_id")
    op.drop_column("tasks", "abort_documentation")
    op.drop_column("tasks", "abort_reason")

    # 11. Remove priority from agents
    op.drop_column("agents", "priority")

    # 12. Update agents: gm -> manager, delete om
    op.execute(sa.text("UPDATE agents SET role = 'manager' WHERE role = 'gm'"))
    op.execute(sa.text("DELETE FROM agents WHERE role = 'om'"))


def downgrade() -> None:
    # Recreate priority and abort columns/tables in reverse order; data from channel_messages
    # cannot be fully restored to chat_messages/tickets, so downgrade is lossy.
    op.execute(sa.text("UPDATE agents SET role = 'gm' WHERE role = 'manager'"))
    op.add_column("agents", sa.Column("priority", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("tasks", sa.Column("abort_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("abort_documentation", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("aborted_by_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_tasks_aborted_by_id_agents", "tasks", "agents", ["aborted_by_id"], ["id"], ondelete="SET NULL"
    )

    op.create_table(
        "engineer_jobs",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tickets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("to_agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("header", sa.String(255), nullable=False),
        sa.Column("ticket_type", sa.String(50), nullable=False),
        sa.Column("critical", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("urgent", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["closed_by_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ticket_messages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("from_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachments", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.drop_index("ix_agent_messages_session", "agent_messages")
    op.drop_index("ix_agent_messages_agent_time", "agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_sessions_status", "agent_sessions")
    op.drop_index("ix_agent_sessions_agent", "agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_index("ix_channel_project", "channel_messages")
    op.drop_index("ix_channel_target_status", "channel_messages")
    op.drop_table("channel_messages")
    op.drop_column("agents", "memory")
    op.drop_index("ix_project_settings_project_id", "project_settings")
    op.drop_table("project_settings")
