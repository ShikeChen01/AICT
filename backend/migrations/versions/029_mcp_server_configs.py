"""Add MCP server configs and extend tool_configs with source/mcp_server_id.

Revision ID: 029
Revises: 028_sandbox_table
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "029"
down_revision = "028_sandbox_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.LargeBinary(), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "status", sa.String(30), default="disconnected", nullable=False
        ),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("tool_count", sa.Integer(), default=0, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_mcp_server_configs_agent", "mcp_server_configs", ["agent_id"]
    )

    # Extend tool_configs with source discrimination
    op.add_column(
        "tool_configs",
        sa.Column("source", sa.String(20), server_default="native", nullable=False),
    )
    op.add_column(
        "tool_configs",
        sa.Column(
            "mcp_server_id",
            sa.Uuid(),
            sa.ForeignKey("mcp_server_configs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tool_configs_mcp_server", "tool_configs", ["mcp_server_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tool_configs_mcp_server", table_name="tool_configs")
    op.drop_column("tool_configs", "mcp_server_id")
    op.drop_column("tool_configs", "source")
    op.drop_index("ix_mcp_server_configs_agent", table_name="mcp_server_configs")
    op.drop_table("mcp_server_configs")
