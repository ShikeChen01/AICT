"""Phase 18: Agent Token Allocations — per-agent dynamic pool overrides.

Introduces:
- token_allocations JSONB column on agents table (nullable)
  Shape: { incoming_msg_tokens: int, memory_pct: float, past_session_pct: float,
           current_session_pct: float }
  NULL = use system defaults from assembly.py constants.

Revision ID: 018_agent_token_allocations
Revises: 017_tool_configs
Create Date: 2026-03-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "018_agent_token_allocations"
down_revision: str = "017_tool_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("token_allocations", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "token_allocations")
