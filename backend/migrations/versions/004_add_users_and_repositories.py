"""Add users and rename projects to repositories.

Revision ID: 004_add_users_and_repositories
Revises: 003_add_engineer_jobs
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "004_add_users_and_repositories"
down_revision = "003_add_engineer_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("github_token", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.rename_table("projects", "repositories")
    op.add_column("repositories", sa.Column("owner_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_repositories_owner_id_users",
        "repositories",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )

    with op.batch_alter_table("repositories") as batch_op:
        batch_op.drop_column("git_token")


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.add_column(sa.Column("git_token", sa.String(length=512), nullable=True))

    op.drop_constraint("fk_repositories_owner_id_users", "repositories", type_="foreignkey")
    op.drop_column("repositories", "owner_id")
    op.rename_table("repositories", "projects")
    op.drop_table("users")
