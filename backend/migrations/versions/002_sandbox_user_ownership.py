"""v3.1-001/002: Add user ownership to sandboxes, add sandbox_file_saves, add project_defaults.

Phase 1 of the v3.1 refactoring: sandbox independence.
  - sandboxes.user_id (NOT NULL after backfill)
  - sandboxes.name, sandboxes.description
  - sandboxes.project_id becomes nullable
  - New table: sandbox_file_saves
  - New table: project_defaults

All steps are idempotent: safe to run against a database that was re-stamped
from the old migration chain (001–029 → 001_baseline).

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


def _column_exists(table: str, column: str) -> bool:
    """Check whether a column already exists (Postgres only)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    """Check whether a table already exists (Postgres only)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :table"
        ),
        {"table": table},
    )
    return result.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    """Check whether an index already exists (Postgres only)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    )
    return result.fetchone() is not None


def _fk_exists(constraint_name: str) -> bool:
    """Check whether a foreign key constraint already exists (Postgres only)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = :name AND constraint_type = 'FOREIGN KEY'"
        ),
        {"name": constraint_name},
    )
    return result.fetchone() is not None


def _column_is_nullable(table: str, column: str) -> bool:
    """Check whether a column is nullable (Postgres only)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    row = result.fetchone()
    return row is not None and row[0] == "YES"


def upgrade() -> None:
    # ── Step 1: Add new columns to sandboxes ─────────────────────────
    if not _column_exists("sandboxes", "user_id"):
        op.add_column("sandboxes", sa.Column("user_id", sa.Uuid(), nullable=True))
    if not _column_exists("sandboxes", "name"):
        op.add_column("sandboxes", sa.Column("name", sa.String(100), nullable=True))
    if not _column_exists("sandboxes", "description"):
        op.add_column("sandboxes", sa.Column("description", sa.Text(), nullable=True))

    # ── Step 2: Backfill user_id from project owner ──────────────────
    # Safe to run multiple times: only touches rows where user_id IS NULL.
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
    # Fallback: orphan sandboxes get the first user.  No-op if subquery is NULL
    # (empty users table) or no sandboxes remain with user_id IS NULL.
    op.execute(
        """
        UPDATE sandboxes
        SET user_id = sub.first_user
        FROM (SELECT id AS first_user FROM users ORDER BY created_at LIMIT 1) sub
        WHERE sandboxes.user_id IS NULL
        """
    )
    # Delete any sandboxes that still have no user_id (no users in DB at all).
    # This prevents the NOT NULL constraint from failing on an empty-users DB.
    op.execute("DELETE FROM sandboxes WHERE user_id IS NULL")

    # ── Step 3: Make user_id NOT NULL and add FK ─────────────────────
    if _column_is_nullable("sandboxes", "user_id"):
        op.alter_column("sandboxes", "user_id", nullable=False)
    if not _fk_exists("fk_sandboxes_user_id"):
        op.create_foreign_key(
            "fk_sandboxes_user_id",
            "sandboxes",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ── Step 4: Make project_id nullable ─────────────────────────────
    # Drop the old CASCADE FK (auto-named by the baseline), recreate as SET NULL.
    if _fk_exists("sandboxes_project_id_fkey"):
        op.drop_constraint("sandboxes_project_id_fkey", "sandboxes", type_="foreignkey")
    if not _column_is_nullable("sandboxes", "project_id"):
        op.alter_column("sandboxes", "project_id", nullable=True)
    if not _fk_exists("fk_sandboxes_project_id"):
        op.create_foreign_key(
            "fk_sandboxes_project_id",
            "sandboxes",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ── Step 5: Index for user sandbox fleet ─────────────────────────
    if not _index_exists("ix_sandboxes_user_status"):
        op.create_index("ix_sandboxes_user_status", "sandboxes", ["user_id", "status"])

    # ── Step 6: Create sandbox_file_saves table ──────────────────────
    if not _table_exists("sandbox_file_saves"):
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
    if not _index_exists("ix_sandbox_file_saves_user"):
        op.create_index("ix_sandbox_file_saves_user", "sandbox_file_saves", ["user_id", "created_at"])

    # ── Step 7: Create project_defaults table ────────────────────────
    if not _table_exists("project_defaults"):
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
