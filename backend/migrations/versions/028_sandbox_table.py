"""Phase 28: Sandbox HPA Implementation — Main sandbox tables and data migration.

Introduces:
- sandbox table: runtime sandboxes (one per agent execution)
- sandbox_snapshot table: snapshots of sandbox state for rollback/restore
- sandbox_usage_event table: cost tracking and pod utilization metrics
- Data migration: Migrate agents with sandbox_id to new sandbox table
- Drop deprecated columns: agent.sandbox_id and agent.sandbox_persist

Revision ID: 028_sandbox_table
Revises: 027_add_composite_indexes
Create Date: 2026-03-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "028_sandbox_table"
down_revision: str = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create sandbox tables and migrate data from agent.sandbox_id."""
    conn = op.get_bind()

    # ── 1. Create sandbox table ──────────────────────────────────────────
    op.create_table(
        "sandbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sandbox_config_id",
            sa.Uuid(),
            sa.ForeignKey("sandbox_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("orchestrator_sandbox_id", sa.String(255), nullable=False, unique=True),
        sa.Column("os_image", sa.String(100), nullable=False, server_default="ubuntu-22.04"),
        sa.Column("setup_script", sa.Text(), nullable=True),
        sa.Column("persistent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(50), nullable=False, server_default="provisioning"),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False, server_default="8080"),
        sa.Column("auth_token", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes on sandbox table
    op.create_index("ix_sandbox_project_id", "sandbox", ["project_id"])
    op.create_index("ix_sandbox_agent_id", "sandbox", ["agent_id"])
    op.create_index("ix_sandbox_status", "sandbox", ["status"])
    # Partial index for unassigned sandboxes (where agent_id IS NULL)
    op.create_index(
        "ix_sandbox_project_status_unassigned",
        "sandbox",
        ["project_id", "status"],
        postgresql_where=sa.text("agent_id IS NULL"),
    )

    # ── 2. Create sandbox_snapshot table ─────────────────────────────────
    op.create_table(
        "sandbox_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sandbox_id",
            sa.Uuid(),
            sa.ForeignKey("sandbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("k8s_snapshot_name", sa.String(255), nullable=False),
        sa.Column("os_image", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes on sandbox_snapshot
    op.create_index("ix_sandbox_snapshot_sandbox_id", "sandbox_snapshot", ["sandbox_id"])
    op.create_index("ix_sandbox_snapshot_project_id", "sandbox_snapshot", ["project_id"])

    # ── 3. Create sandbox_usage_event table ──────────────────────────────
    op.create_table(
        "sandbox_usage_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sandbox_id",
            sa.Uuid(),
            sa.ForeignKey("sandbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("pod_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes on sandbox_usage_event
    op.create_index("ix_sandbox_usage_sandbox_id", "sandbox_usage_event", ["sandbox_id"])
    op.create_index("ix_sandbox_usage_project_id", "sandbox_usage_event", ["project_id"])
    op.create_index("ix_sandbox_usage_event_type", "sandbox_usage_event", ["event_type"])

    # ── 4. Data migration: Migrate agents with sandbox_id to sandbox table ──
    # For each agent with a non-NULL sandbox_id, create a sandbox record with status='assigned'
    op.execute(
        sa.text("""
            INSERT INTO sandbox (id, project_id, agent_id, sandbox_config_id,
                                orchestrator_sandbox_id, os_image, setup_script,
                                persistent, status, created_at, assigned_at)
            SELECT
                gen_random_uuid(),
                a.project_id,
                a.id,
                a.sandbox_config_id,
                COALESCE(a.sandbox_id, 'migrated-' || gen_random_uuid()::text),
                COALESCE(sc.os_image, 'ubuntu-22.04'),
                sc.setup_script,
                COALESCE(a.sandbox_persist, false),
                'assigned',
                now(),
                now()
            FROM agents a
            LEFT JOIN sandbox_configs sc ON a.sandbox_config_id = sc.id
            WHERE a.sandbox_id IS NOT NULL
        """)
    )

    # ── 5. Drop deprecated columns from agents table ──────────────────────
    op.drop_column("agents", "sandbox_persist")
    op.drop_column("agents", "sandbox_id")


def downgrade() -> None:
    """Rollback: restore agent columns and drop sandbox tables."""

    # ── 1. Restore agent columns ─────────────────────────────────────────
    op.add_column(
        "agents",
        sa.Column("sandbox_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("sandbox_persist", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── 2. Data migration: Copy sandbox back to agents table ───────────────
    # For each sandbox assigned to an agent, restore sandbox_id and sandbox_persist
    op.execute(
        sa.text("""
            UPDATE agents a
            SET sandbox_id = s.orchestrator_sandbox_id,
                sandbox_persist = s.persistent
            FROM sandbox s
            WHERE s.agent_id = a.id
                AND s.status = 'assigned'
        """)
    )

    # ── 3. Drop sandbox tables ───────────────────────────────────────────
    op.drop_index("ix_sandbox_usage_event_type", table_name="sandbox_usage_event")
    op.drop_index("ix_sandbox_usage_project_id", table_name="sandbox_usage_event")
    op.drop_index("ix_sandbox_usage_sandbox_id", table_name="sandbox_usage_event")
    op.drop_table("sandbox_usage_event")

    op.drop_index("ix_sandbox_snapshot_project_id", table_name="sandbox_snapshot")
    op.drop_index("ix_sandbox_snapshot_sandbox_id", table_name="sandbox_snapshot")
    op.drop_table("sandbox_snapshot")

    op.drop_index("ix_sandbox_project_status_unassigned", table_name="sandbox")
    op.drop_index("ix_sandbox_status", table_name="sandbox")
    op.drop_index("ix_sandbox_agent_id", table_name="sandbox")
    op.drop_index("ix_sandbox_project_id", table_name="sandbox")
    op.drop_table("sandbox")
