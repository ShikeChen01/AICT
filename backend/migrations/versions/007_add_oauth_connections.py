"""Add user_oauth_connections table and widen firebase_uid.

Revision ID: 007_oauth
Revises: 006_add_v5_api_keys_and_billing
"""

revision = "007_oauth"
down_revision = "006_add_v5_api_keys_and_billing"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.alter_column(
        "users",
        "firebase_uid",
        existing_type=sa.String(128),
        type_=sa.String(255),
    )

    op.create_table(
        "user_oauth_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_conn_user_provider"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_conn_provider_ext_id"),
    )
    op.create_index("ix_oauth_conn_user", "user_oauth_connections", ["user_id"])


def downgrade():
    op.drop_index("ix_oauth_conn_user")
    op.drop_table("user_oauth_connections")
    op.alter_column(
        "users",
        "firebase_uid",
        existing_type=sa.String(255),
        type_=sa.String(128),
    )
