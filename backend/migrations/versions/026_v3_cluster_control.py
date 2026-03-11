"""Phase 26: v3 Agent Cluster Control — new tables and columns.

New tables:
  cluster_specs             Persisted ClusterSpec manifests (YAML) for drift detection
  dead_letter_messages      Messages that failed delivery after MAX_NOTIFY_ATTEMPTS
  sandbox_usage_events      Sandbox pod-second metering records

New columns (none — the os_image column on sandbox_configs was added in a prior session).

Revision ID: 026
Revises: 025
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # cluster_specs: persisted cluster manifest YAML for drift detection
    # ----------------------------------------------------------------
    op.create_table(
        "cluster_specs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_name", sa.String(100), nullable=False),
        sa.Column("spec_yaml", sa.Text, nullable=False),
        sa.Column("applied_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_cluster_specs_project", "cluster_specs", ["project_id"])
    op.create_unique_constraint(
        "uq_cluster_specs_project_name", "cluster_specs", ["project_id", "cluster_name"]
    )

    # ----------------------------------------------------------------
    # dead_letter_messages: messages that could not be delivered
    # ----------------------------------------------------------------
    op.create_table(
        "dead_letter_messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("target_agent_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_message_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_dlq_agent", "dead_letter_messages", ["target_agent_id"])
    op.create_index("ix_dlq_unresolved", "dead_letter_messages", ["resolved_at"],
                    postgresql_where=sa.text("resolved_at IS NULL"))

    # ----------------------------------------------------------------
    # sandbox_usage_events: pod-second metering records
    # ----------------------------------------------------------------
    op.create_table(
        "sandbox_usage_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sandbox_id", sa.String(255), nullable=True),
        sa.Column("pod_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(50), nullable=False, server_default="session_end"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_sandbox_usage_project_time", "sandbox_usage_events",
                    ["project_id", "created_at"])
    op.create_index("ix_sandbox_usage_agent", "sandbox_usage_events", ["agent_id"])


def downgrade() -> None:
    op.drop_table("sandbox_usage_events")
    op.drop_table("dead_letter_messages")
    op.drop_table("cluster_specs")
