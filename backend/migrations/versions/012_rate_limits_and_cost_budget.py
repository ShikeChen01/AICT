"""Phase 4b: per-project rate limiting and cost budget.

Adds three columns to project_settings:

  calls_per_hour_limit   INT     — max LLM API calls in a rolling 60-min window (0 = off)
  tokens_per_hour_limit  INT     — max tokens (input+output) in a rolling 60-min window (0 = off)
  daily_cost_budget_usd  FLOAT   — max estimated USD spend per day UTC (0.0 = off)

When a rate limit fires the agent loop soft-pauses (sleeps 5 s, re-checks DB).
Adjusting limits from the frontend is reflected within one poll cycle (~5 s).
When the cost budget is exhausted the session ends immediately (hard stop).

Revision ID: 012_rate_limits_cost_budget
Revises: 011_llm_usage_events
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_rate_limits_cost_budget"
down_revision: str | None = "011_llm_usage_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_settings",
        sa.Column(
            "calls_per_hour_limit",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Max LLM calls in rolling 60-min window per project. 0 = unlimited.",
        ),
    )
    op.add_column(
        "project_settings",
        sa.Column(
            "tokens_per_hour_limit",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Max tokens (input+output) in rolling 60-min window per project. 0 = unlimited.",
        ),
    )
    op.add_column(
        "project_settings",
        sa.Column(
            "daily_cost_budget_usd",
            sa.Float,
            nullable=False,
            server_default="0.0",
            comment="Max estimated USD spend per day (UTC). 0.0 = unlimited.",
        ),
    )


def downgrade() -> None:
    op.drop_column("project_settings", "daily_cost_budget_usd")
    op.drop_column("project_settings", "tokens_per_hour_limit")
    op.drop_column("project_settings", "calls_per_hour_limit")
