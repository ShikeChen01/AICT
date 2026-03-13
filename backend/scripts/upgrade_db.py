"""
Upgrade the database to the current Alembic head.

This wrapper keeps normal Alembic behavior for fresh databases, but it also
handles one legacy case from the pre-baseline migration chain:

- Databases stamped anywhere in the old 024-029 chain can no longer be upgraded
  directly once the chain is replaced by `001_baseline`.
- For those databases, we imperatively converge the schema to the baseline
  shape, rewrite `alembic_version` to `001_baseline`, then continue with
  `alembic upgrade head`.

The convergence is intentionally idempotent so it is safe to re-run.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

LEGACY_REVISIONS = {
    "024_rag_knowledge_base",
    "025_enable_pgvector_column",
    "026",
    "027",
    "028_sandbox_table",
    "029",
}
BASELINE_REVISION = "001_baseline"


def build_sync_database_url(async_database_url: str) -> str:
    """Convert the app's asyncpg URL into a sync URL for imperative SQL."""
    sync_url = make_url(async_database_url).set(drivername="postgresql+psycopg2")
    query = dict(sync_url.query)

    if os.getenv("DB_SSL_MODE", "").lower() == "require":
        query.setdefault("sslmode", "require")

    return sync_url.set(query=query).render_as_string(hide_password=False)


def current_revision(conn) -> str | None:
    has_table = conn.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    if not has_table:
        return None

    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def has_table(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{table_name}"},
        ).scalar()
    )


def has_column(conn, table_name: str, column_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                )
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
    )


def has_constraint(conn, table_name: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    WHERE n.nspname = 'public'
                      AND t.relname = :table_name
                      AND c.conname = :constraint_name
                )
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalar()
    )


def needs_legacy_transition(revision: str | None) -> bool:
    return revision in LEGACY_REVISIONS


def ensure_pgvector_and_embeddings(conn) -> None:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    if not has_table(conn, "knowledge_chunks"):
        return

    embedding_udt = conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'knowledge_chunks'
              AND column_name = 'embedding'
            """
        )
    ).scalar()

    if embedding_udt != "vector":
        conn.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw"))
        conn.execute(
            text("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024)")
        )

    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_knowledge_chunks_doc_idx
            ON knowledge_chunks (document_id, chunk_index)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_project
            ON knowledge_chunks (project_id, created_at)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw
            ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        )
    )


def ensure_hot_path_indexes(conn) -> None:
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_agents_project_status
            ON agents (project_id, status)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_agents_project_role
            ON agents (project_id, role)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tasks_project_status
            ON tasks (project_id, status)
            """
        )
    )


def ensure_task_agent_relationships(conn) -> None:
    if has_column(conn, "tasks", "assigned_agent_id") and not has_constraint(
        conn, "tasks", "fk_tasks_assigned_agent"
    ):
        conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD CONSTRAINT fk_tasks_assigned_agent
                FOREIGN KEY (assigned_agent_id) REFERENCES agents(id)
                ON DELETE SET NULL
                """
            )
        )

    if has_column(conn, "tasks", "created_by_id") and not has_constraint(
        conn, "tasks", "fk_tasks_created_by"
    ):
        conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD CONSTRAINT fk_tasks_created_by
                FOREIGN KEY (created_by_id) REFERENCES agents(id)
                ON DELETE SET NULL
                """
            )
        )


def ensure_sandbox_tables(conn) -> None:
    # Ensure sandbox_configs has the os_image and setup_script columns before we
    # try to read them during migrate_agent_sandbox_columns().  These were added
    # to sandbox_configs in the old incremental chain *before* the sandbox table
    # was introduced, so a DB that never ran those migrations won't have them.
    conn.execute(
        text(
            """
            ALTER TABLE sandbox_configs
            ADD COLUMN IF NOT EXISTS os_image varchar(50) NULL
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE sandbox_configs
            ADD COLUMN IF NOT EXISTS setup_script text NOT NULL DEFAULT ''
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sandbox (
                id uuid PRIMARY KEY,
                project_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                agent_id uuid NULL REFERENCES agents(id) ON DELETE SET NULL,
                sandbox_config_id uuid NULL REFERENCES sandbox_configs(id) ON DELETE SET NULL,
                orchestrator_sandbox_id varchar(255) NOT NULL UNIQUE,
                os_image varchar(100) NOT NULL DEFAULT 'ubuntu-22.04',
                setup_script text NULL,
                persistent boolean NOT NULL DEFAULT false,
                status varchar(50) NOT NULL DEFAULT 'provisioning',
                host varchar(255) NULL,
                port integer DEFAULT 8080,
                auth_token varchar(512) NULL,
                created_at timestamptz NOT NULL,
                assigned_at timestamptz NULL,
                last_health_at timestamptz NULL,
                released_at timestamptz NULL
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sandbox_snapshot (
                id uuid PRIMARY KEY,
                sandbox_id uuid NOT NULL REFERENCES sandbox(id) ON DELETE CASCADE,
                project_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                agent_id uuid NULL REFERENCES agents(id) ON DELETE SET NULL,
                k8s_snapshot_name varchar(255) NOT NULL,
                os_image varchar(100) NOT NULL,
                label varchar(255) NULL,
                size_bytes bigint NULL,
                created_at timestamptz NOT NULL
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sandbox_usage_event (
                id uuid PRIMARY KEY,
                sandbox_id uuid NOT NULL REFERENCES sandbox(id) ON DELETE CASCADE,
                project_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                agent_id uuid NULL REFERENCES agents(id) ON DELETE SET NULL,
                event_type varchar(50) NOT NULL,
                pod_seconds double precision NOT NULL DEFAULT 0,
                cost_usd double precision NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL
            )
            """
        )
    )


def migrate_agent_sandbox_columns(conn) -> None:
    sandbox_id_present = has_column(conn, "agents", "sandbox_id")
    sandbox_persist_present = has_column(conn, "agents", "sandbox_persist")
    if not sandbox_id_present:
        return

    # By this point ensure_sandbox_tables() has run ADD COLUMN IF NOT EXISTS for
    # sandbox_configs.os_image and sandbox_configs.setup_script, so the JOIN is safe.
    rows = conn.execute(
        text(
            """
            SELECT
                a.id AS agent_id,
                a.project_id,
                a.sandbox_config_id,
                a.sandbox_id,
                COALESCE(a.sandbox_persist, false) AS sandbox_persist,
                sc.os_image AS os_image,
                sc.setup_script AS setup_script
            FROM agents a
            LEFT JOIN sandbox_configs sc ON sc.id = a.sandbox_config_id
            WHERE a.sandbox_id IS NOT NULL
            """
        )
    ).mappings()

    for row in rows:
        conn.execute(
            text(
                """
                INSERT INTO sandbox (
                    id,
                    project_id,
                    agent_id,
                    sandbox_config_id,
                    orchestrator_sandbox_id,
                    os_image,
                    setup_script,
                    persistent,
                    status,
                    created_at,
                    assigned_at
                )
                SELECT
                    :id,
                    :project_id,
                    :agent_id,
                    :sandbox_config_id,
                    :orchestrator_sandbox_id,
                    :os_image,
                    :setup_script,
                    :persistent,
                    'assigned',
                    NOW(),
                    NOW()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM sandbox
                    WHERE agent_id = :agent_id
                       OR orchestrator_sandbox_id = :orchestrator_sandbox_id
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "project_id": row["project_id"],
                "agent_id": row["agent_id"],
                "sandbox_config_id": row["sandbox_config_id"],
                "orchestrator_sandbox_id": row["sandbox_id"],
                "os_image": row["os_image"] or "ubuntu-22.04",
                "setup_script": row["setup_script"],
                "persistent": row["sandbox_persist"],
            },
        )

    if sandbox_persist_present:
        conn.execute(text("ALTER TABLE agents DROP COLUMN IF EXISTS sandbox_persist"))
    conn.execute(text("ALTER TABLE agents DROP COLUMN IF EXISTS sandbox_id"))


def ensure_mcp_server_support(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mcp_server_configs (
                id uuid PRIMARY KEY,
                agent_id uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                name varchar(120) NOT NULL,
                url text NOT NULL,
                api_key bytea NULL,
                headers json NULL,
                enabled boolean NOT NULL DEFAULT true,
                status varchar(30) NOT NULL DEFAULT 'disconnected',
                status_detail text NULL,
                tool_count integer NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL,
                updated_at timestamptz NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_mcp_server_configs_agent
            ON mcp_server_configs (agent_id)
            """
        )
    )

    if not has_column(conn, "tool_configs", "source"):
        conn.execute(
            text(
                """
                ALTER TABLE tool_configs
                ADD COLUMN source varchar(20) NOT NULL DEFAULT 'native'
                """
            )
        )

    if not has_column(conn, "tool_configs", "mcp_server_id"):
        conn.execute(
            text("ALTER TABLE tool_configs ADD COLUMN mcp_server_id uuid NULL")
        )

    if not has_constraint(conn, "tool_configs", "tool_configs_mcp_server_id_fkey"):
        conn.execute(
            text(
                """
                ALTER TABLE tool_configs
                ADD CONSTRAINT tool_configs_mcp_server_id_fkey
                FOREIGN KEY (mcp_server_id) REFERENCES mcp_server_configs(id)
                ON DELETE CASCADE
                """
            )
        )

    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tool_configs_mcp_server
            ON tool_configs (mcp_server_id)
            """
        )
    )


def stamp_baseline(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL
            )
            """
        )
    )
    conn.execute(text("DELETE FROM alembic_version"))
    conn.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": BASELINE_REVISION},
    )


def transition_legacy_chain_to_baseline(sync_database_url: str) -> None:
    engine = create_engine(sync_database_url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            revision = current_revision(conn)
            if not needs_legacy_transition(revision):
                return

            ensure_pgvector_and_embeddings(conn)
            ensure_hot_path_indexes(conn)
            ensure_task_agent_relationships(conn)
            ensure_sandbox_tables(conn)
            migrate_agent_sandbox_columns(conn)
            ensure_mcp_server_support(conn)
            stamp_baseline(conn)
    finally:
        engine.dispose()


def run_alembic_upgrade() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    script_location = repo_root / "backend" / "migrations"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(script_location))
    command.upgrade(cfg, "head")


def upgrade_db() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations.")

    sync_database_url = build_sync_database_url(database_url)
    transition_legacy_chain_to_baseline(sync_database_url)
    run_alembic_upgrade()


def main() -> int:
    upgrade_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
