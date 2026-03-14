"""v3.1-001/002: Add user ownership to sandboxes, add sandbox_file_saves, add project_defaults.

Phase 1 of the v3.1 refactoring: sandbox independence.
  - sandboxes.user_id (NOT NULL after backfill)
  - sandboxes.name, sandboxes.description
  - sandboxes.project_id becomes nullable
  - New table: sandbox_file_saves
  - New table: project_defaults

Revision ID: 002_sandbox_user_ownership
Revises: 001_baseline
Create Date: 2026-03-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_sandbox_user_ownership"
down_revision: str = "001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Step 1: Add new columns to sandboxes ─────────────────────────
    # user_id starts nullable so we can backfill before adding NOT NULL
    op.add_column("sandboxes", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("sandboxes", sa.Column("name", sa.String(100), nullable=True))
    op.add_column("sandboxes", sa.Column("description", sa.Text(), nullable=True))

    # ── Step 2: Backfill user_id from project owner ──────────────────
    op.execute(
        """
        UPDATE sandboxes s
        SET user_id = p.owner_id
        FROM projects p
        WHERE s.project_id = p.id
          AND s.user_id IS NULL
          AND p.owner_id IS NOT NULL
        """
    )
    # For any sandboxes whose project has no owner, set to first user as fallback
    op.execute(
        """
        UPDATE sandboxes
        SET user_id = (SELECT id FROM users ORDER BY created_at LIMIT 1)
        WHERE user_id IS NULL
        """
    )

    # ── Step 3: Make user_id NOT NULL and add FK ─────────────────────
    op.alter_column("sandboxes", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_sandboxes_user_id",
        "sandboxes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── Step 4: Make project_id nullable ─────────────────────────────
    # Drop the existing CASCADE FK first, recreate as SET NULL
    op.drop_constraint("sandboxes_project_id_fkey", "sandboxes", type_="foreignkey")
    op.alter_column("sandboxes", "project_id", nullable=True)
    op.create_foreign_key(
        "fk_sandboxes_project_id",
        "sandboxes",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Step 5: Index for user sandbox fleet ─────────────────────────
    op.create_index("ix_sandboxes_user_status", "sandboxes", ["user_id", "status"])

    # ── Step 6: Create sandbox_file_saves table ──────────────────────
    op.create_table(
        "sandbox_file_saves",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sandbox_id", sa.Uuid(), sa.ForeignKey("sandboxes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sandbox_file_saves_user", "sandbox_file_saves", ["user_id", "created_at"])

    # ── Step 7: Create project_defaults table ────────────────────────
    op.create_table(
        "project_defaults",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("default_template_id", sa.Uuid(), sa.ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("project_defaults")
    op.drop_index("ix_sandbox_file_saves_user", "sandbox_file_saves")
    op.drop_table("sandbox_file_saves")
    op.drop_index("ix_sandboxes_user_status", "sandboxes")

    # Restore project_id to NOT NULL with CASCADE
    op.drop_constraint("fk_sandboxes_project_id", "sandboxes", type_="foreignkey")
    op.alter_column("sandboxes", "project_id", nullable=False)
    op.create_foreign_key(
        "sandboxes_project_id_fkey",
        "sandboxes",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("fk_sandboxes_user_id", "sandboxes", type_="foreignkey")
    op.drop_column("sandboxes", "description")
    op.drop_column("sandboxes", "name")
    op.drop_column("sandboxes", "user_id")
