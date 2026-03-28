"""Add partial unique index on sandboxes (agent_id, unit_type).

Ensures each agent has at most one headless sandbox and one desktop sandbox.

Revision ID: 008_desktop_idx
Revises: 007_oauth
"""

revision = "008_desktop_idx"
down_revision = "007_oauth"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_index(
        "uq_sandbox_agent_unit_type",
        "sandboxes",
        ["agent_id", "unit_type"],
        unique=True,
        postgresql_where=sa.text("agent_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("uq_sandbox_agent_unit_type", table_name="sandboxes")
