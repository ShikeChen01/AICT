"""v5-006: Add per-user API keys and billing tables.

Revision ID: 006_add_v5
Revises: 005_add_target_user_id_remove_sentinel
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_add_v5"
down_revision: str = "005_add_target_user_id_remove_sentinel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── User columns ──────────────────────────────────────────────────
    op.add_column("users", sa.Column("tier", sa.String(20), nullable=False, server_default="free"))
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))

    # ── User API keys table ───────────────────────────────────────────
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("display_hint", sa.String(20), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
    )

    # ── Subscriptions table ───────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_stripe_customer", "subscriptions", ["stripe_customer_id"])
    op.create_index("ix_subscriptions_stripe_sub", "subscriptions", ["stripe_subscription_id"])

    # ── Usage periods table ───────────────────────────────────────────
    op.create_table(
        "usage_periods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headless_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("desktop_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period_start", name="uq_usage_period_user_start"),
    )

    # ── SandboxUsageEvent.unit_type ──────────────────────────────────
    op.add_column(
        "sandbox_usage_events",
        sa.Column("unit_type", sa.String(20), nullable=False, server_default="headless"),
    )


def downgrade() -> None:
    op.drop_column("sandbox_usage_events", "unit_type")
    op.drop_table("usage_periods")
    op.drop_table("subscriptions")
    op.drop_table("user_api_keys")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "tier")
