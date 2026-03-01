"""Phase 16: Project document versioning and user editing.

Introduces:
- document_versions table: full content snapshots per document
- project_documents.updated_by_user_id: track user vs agent edits
- project_documents.current_version: current version number
- Seeds initial version row (version_number=1) for all existing documents

Revision ID: 016_document_versioning
Revises: 015_agent_templates
Create Date: 2026-03-01
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_document_versioning"
down_revision: str | None = "015_agent_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Create document_versions table ────────────────────────────────────
    op.create_table(
        "document_versions",
        sa.Column(
            "id", sa.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("project_documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "edited_by_agent_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "edited_by_user_id", sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("edit_summary", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_document_versions_doc_num", "document_versions",
        ["document_id", "version_number"], unique=True,
    )
    op.create_index(
        "ix_document_versions_doc_time", "document_versions",
        ["document_id", "created_at"],
    )

    # ── 2. Add columns to project_documents ──────────────────────────────────
    op.add_column("project_documents", sa.Column(
        "updated_by_user_id", sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("project_documents", sa.Column(
        "current_version", sa.Integer, nullable=False, server_default="1",
    ))

    # ── 3. Seed initial version row for existing documents ────────────────────
    existing_docs = conn.execute(
        sa.text("""
            SELECT id, content, title, updated_by_agent_id, updated_at
            FROM project_documents
            WHERE content IS NOT NULL
        """)
    ).fetchall()

    for doc in existing_docs:
        conn.execute(sa.text("""
            INSERT INTO document_versions
                (id, document_id, version_number, content, title,
                 edited_by_agent_id, edited_by_user_id, edit_summary, created_at)
            VALUES
                (:id, :document_id, 1, :content, :title,
                 :edited_by_agent_id, NULL, 'Initial version', :created_at)
        """), {
            "id": str(uuid.uuid4()),
            "document_id": str(doc[0]),
            "content": doc[1],
            "title": doc[2],
            "edited_by_agent_id": str(doc[3]) if doc[3] else None,
            "created_at": doc[4],
        })


def downgrade() -> None:
    op.drop_column("project_documents", "current_version")
    op.drop_column("project_documents", "updated_by_user_id")

    op.drop_index("ix_document_versions_doc_time", table_name="document_versions")
    op.drop_index("ix_document_versions_doc_num", table_name="document_versions")
    op.drop_table("document_versions")
