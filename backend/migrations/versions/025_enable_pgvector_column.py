"""Phase 25: Upgrade knowledge_chunks.embedding jsonb → vector(1024).

Run this migration AFTER installing pgvector on the Postgres host
(i.e. after switching the Docker image to pgvector/pgvector:pg16 and
restarting the container).

If pgvector is still not available this migration fails with a clear
error rather than silently continuing.

How to apply:
  1. SSH into the Postgres VM and run:
       sudo docker compose -f /opt/postgres/compose/docker-compose.yml pull
       sudo docker compose -f /opt/postgres/compose/docker-compose.yml up -d --force-recreate
  2. Then re-run migrations:
       scripts/cloud/migrate.ps1

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from sqlalchemy import text, inspect
from alembic import op

revision = "025_enable_pgvector_column"
down_revision = "024_rag_knowledge_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Check if pgvector is already enabled ───────────────────────────
    result = conn.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if result and result > 0:
        # Already enabled — nothing to do for extension
        pass
    else:
        # Try to create it — will raise clearly if server doesn't have it
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # ── 2. Check if embedding column is already vector type ───────────────
    col_type = conn.execute(text("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'knowledge_chunks' AND column_name = 'embedding'
    """)).scalar()

    if col_type in ("jsonb", "json", "text", None):
        # Upgrade: drop existing jsonb column and add proper vector column.
        # Existing embeddings (if any stored as jsonb) are dropped — they
        # will be re-indexed by re-uploading documents.
        conn.execute(text("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding"))
        conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024)"))

        # HNSW index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw
            ON knowledge_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
    else:
        # Already vector — just make sure the HNSW index exists
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw
            ON knowledge_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw"))
    conn.execute(text("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding"))
    conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN embedding jsonb"))
