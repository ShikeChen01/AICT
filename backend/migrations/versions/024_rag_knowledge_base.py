"""Phase 24: RAG Knowledge Base (Feature 1.6).

Adds the complete RAG stack:
  - Enables pgvector extension for vector similarity search
  - knowledge_documents: uploaded files per project (PDF/TXT/MD/CSV)
  - knowledge_chunks: chunked text with 1024-dim Voyage AI embeddings
  - project_settings additions: knowledge quotas

If pgvector is not yet installed on the PostgreSQL server the migration
still succeeds: the embedding column falls back to ``jsonb`` and the HNSW
index is skipped.  Semantic search returns an empty list in that state
(graceful degradation already in KnowledgeRepository).

To enable full vector search later, install pgvector on the Postgres host
then run migration 025_enable_pgvector_column (see docs/v2/RAG_Implementation_Plan.md).

Revision ID: 024
Revises: 023
"""

import sqlalchemy as sa
from sqlalchemy import text
from alembic import op

revision = "024_rag_knowledge_base"
down_revision = "023_dedup_prompt_blocks"
branch_labels = None
depends_on = None


def _try_enable_pgvector(conn) -> bool:
    """Attempt CREATE EXTENSION vector inside a savepoint.

    Returns True if pgvector is now available, False if the server doesn't
    have it installed (the savepoint is rolled back so the transaction stays clean).
    """
    try:
        conn.execute(text("SAVEPOINT pgvector_ext"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("RELEASE SAVEPOINT pgvector_ext"))
        return True
    except Exception:
        # Roll back only to the savepoint — the outer transaction is unaffected
        conn.execute(text("ROLLBACK TO SAVEPOINT pgvector_ext"))
        return False


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. pgvector extension (graceful: skip if not installed on server) ──
    has_pgvector = _try_enable_pgvector(conn)

    # ── 2. knowledge_documents ───────────────────────────────────────────
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["project_id"], ["repositories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_documents_project_created",
        "knowledge_documents",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_knowledge_documents_project_status",
        "knowledge_documents",
        ["project_id", "status"],
    )

    # ── 3. knowledge_chunks ──────────────────────────────────────────────
    # Use vector(1024) when pgvector is available, jsonb otherwise.
    # The jsonb fallback lets documents be ingested and stored; semantic
    # search returns [] until the column is upgraded to vector(1024).
    embedding_col = "vector(1024)" if has_pgvector else "jsonb"
    conn.execute(text(f"""
        CREATE TABLE knowledge_chunks (
            id          uuid        NOT NULL,
            document_id uuid        NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
            project_id  uuid        NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            chunk_index integer     NOT NULL,
            text_content text       NOT NULL,
            char_count  integer     NOT NULL,
            token_count integer     NOT NULL,
            embedding   {embedding_col},
            metadata_   jsonb,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_knowledge_chunks_doc_idx UNIQUE (document_id, chunk_index)
        )
    """))
    conn.execute(text(
        "CREATE INDEX ix_knowledge_chunks_project "
        "ON knowledge_chunks (project_id, created_at)"
    ))

    if has_pgvector:
        # HNSW index for fast cosine-distance search
        conn.execute(text("""
            CREATE INDEX ix_knowledge_chunks_embedding_hnsw
            ON knowledge_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))

    # ── 4. project_settings additions ────────────────────────────────────
    op.add_column(
        "project_settings",
        sa.Column(
            "knowledge_max_documents",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )
    op.add_column(
        "project_settings",
        sa.Column(
            "knowledge_max_total_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=str(100 * 1024 * 1024),  # 100 MB
        ),
    )

    if not has_pgvector:
        import warnings
        warnings.warn(
            "pgvector extension not available on this PostgreSQL server. "
            "Knowledge Base tables were created but embedding column is jsonb "
            "(semantic search disabled). Install pgvector and run migration "
            "025_enable_pgvector_column to enable full vector search.",
            stacklevel=2,
        )


def downgrade() -> None:
    op.drop_column("project_settings", "knowledge_max_total_bytes")
    op.drop_column("project_settings", "knowledge_max_documents")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
    op.drop_index("ix_knowledge_documents_project_status", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_project_created", "knowledge_documents")
    op.drop_table("knowledge_documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
