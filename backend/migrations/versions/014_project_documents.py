"""Phase 10: per-project architecture document store.

Creates the project_documents table — a typed, manager-agent-writable Markdown
document store for per-project architecture artefacts (source of truth, arc42-lite,
C4 diagrams, ADRs). Users have read-only REST access; write access is exclusively
via the write_architecture_doc agent tool (role=manager only).

Revision ID: 014_project_documents
Revises: 013_attachments
Create Date: 2026-02-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_project_documents"
down_revision: str | None = "013_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_documents",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
            comment="Owning repository. Cascades on project delete.",
        ),
        sa.Column(
            "doc_type",
            sa.String(100),
            nullable=False,
            comment=(
                "Document type identifier. Well-known values: "
                "'architecture_source_of_truth', 'arc42_lite', 'c4_diagrams', 'adr/<slug>'."
            ),
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=True,
            comment="Human-readable document title, set by the manager agent.",
        ),
        sa.Column(
            "content",
            sa.Text,
            nullable=True,
            comment="Raw Markdown content. NULL means the document has not been written yet.",
        ),
        sa.Column(
            "updated_by_agent_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
            comment="The manager agent that last wrote this document.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("project_id", "doc_type", name="uq_project_documents_project_type"),
    )
    op.create_index("ix_project_documents_project", "project_documents", ["project_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_project_documents_project", table_name="project_documents")
    op.drop_table("project_documents")
