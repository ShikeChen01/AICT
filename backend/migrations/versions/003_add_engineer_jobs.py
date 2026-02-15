"""Add engineer_jobs table for background task queue.

Revision ID: 003_add_engineer_jobs
Revises: 002_add_project_git_token
Create Date: 2026-02-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "003_add_engineer_jobs"
down_revision = "002_add_project_git_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineer_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Index for efficient job queue polling
    op.create_index(
        "ix_engineer_jobs_status_created",
        "engineer_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_engineer_jobs_status_created", table_name="engineer_jobs")
    op.drop_table("engineer_jobs")
