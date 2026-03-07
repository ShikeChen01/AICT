"""Phase 22: User-Defined Agent System (Phase 1.2).

Extends agent_templates into full "agent designs" by adding:
  - description: human-readable description of the agent design
  - sandbox_template: sandbox template identifier (e.g., "dev-python", "browser-automation")
  - knowledge_sources: JSON config for RAG knowledge sources
  - trigger_config: JSON config for agent triggers
  - cost_limits: JSON config for cost limits

Relaxes the role system:
  - agent_templates.base_role becomes free-text (removes enum constraint)
  - agents.role becomes free-text (removes enum constraint)
  - Adds 'custom' as a valid base_role alongside existing ones
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "022_agent_designs"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend agent_templates with design fields ─────────────────────

    op.add_column(
        "agent_templates",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_templates",
        sa.Column("sandbox_template", sa.String(100), nullable=True),
    )
    op.add_column(
        "agent_templates",
        sa.Column("knowledge_sources", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_templates",
        sa.Column("trigger_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_templates",
        sa.Column("cost_limits", sa.JSON(), nullable=True),
    )

    # No explicit enum to drop since base_role is just String(50).
    # Mark existing 'worker' templates and future custom templates all valid.


def downgrade() -> None:
    op.drop_column("agent_templates", "cost_limits")
    op.drop_column("agent_templates", "trigger_config")
    op.drop_column("agent_templates", "knowledge_sources")
    op.drop_column("agent_templates", "sandbox_template")
    op.drop_column("agent_templates", "description")
