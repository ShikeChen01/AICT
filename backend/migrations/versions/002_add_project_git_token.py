"""Add git_token column to projects table.

Revision ID: 002_add_project_git_token
Revises: 001_init_mvp0_schema
Create Date: 2026-02-14
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002_add_project_git_token"
down_revision = "001_init_mvp0_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("git_token", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "git_token")
