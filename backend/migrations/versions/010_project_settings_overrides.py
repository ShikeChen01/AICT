"""Phase 3: project_settings model_overrides and prompt_overrides columns.

model_overrides: JSON map of role/tier -> model string (e.g. {"manager": "claude-opus-4-6"}).
  Overrides the global defaults from config.py at the project level.

prompt_overrides: JSON map of role -> additional system prompt text
  (e.g. {"manager": "Always reply in formal English."}).
  Injected as a bounded block at the end of each agent's system prompt.

Revision ID: 010_project_settings_overrides
Revises: 009_memberships_attribution
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "010_project_settings_overrides"
down_revision: str | None = "009_memberships_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_settings",
        sa.Column("model_overrides", JSONB, nullable=True, comment=(
            "Per-role model overrides. Keys: manager, cto, engineer_junior, "
            "engineer_intermediate, engineer_senior. Values: model name strings."
        )),
    )
    op.add_column(
        "project_settings",
        sa.Column("prompt_overrides", JSONB, nullable=True, comment=(
            "Per-role additional system prompt text. Keys: manager, cto, engineer. "
            "Values: plain text injected at end of system prompt (max 2000 chars enforced)."
        )),
    )


def downgrade() -> None:
    op.drop_column("project_settings", "prompt_overrides")
    op.drop_column("project_settings", "model_overrides")
