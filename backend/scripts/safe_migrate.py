"""
Run Alembic migrations with a pgvector-aware target revision.

If the PostgreSQL server does not expose the `vector` extension yet, stop at
revision 024 so the Knowledge Base schema can land without applying the
pgvector-only upgrade in revision 025. Once the server is upgraded to a
pgvector-capable image, rerunning this script will continue to `head`.
"""

from __future__ import annotations

import asyncio
import os
import ssl as _ssl
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


SAFE_FALLBACK_REVISION = "024_rag_knowledge_base"


def _build_connect_args() -> dict:
    """Match the Alembic SSL behavior used in cloud and local environments."""
    ssl_mode = os.getenv("DB_SSL_MODE", "").lower()
    if ssl_mode == "require":
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        return {"ssl": ctx}
    return {}


async def _server_has_pgvector(database_url: str) -> bool:
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args=_build_connect_args(),
    )
    try:
        async with engine.connect() as conn:
            result = await conn.scalar(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
                    ")"
                )
            )
            return bool(result)
    finally:
        await engine.dispose()


def choose_target_revision(has_pgvector: bool) -> str:
    return "head" if has_pgvector else SAFE_FALLBACK_REVISION


def inspect_pgvector_available(database_url: str) -> bool:
    return asyncio.run(_server_has_pgvector(database_url))


def run_alembic_upgrade(target_revision: str) -> int:
    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        "backend/alembic.ini",
        "upgrade",
        target_revision,
    ]
    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required to run migrations.", file=sys.stderr)
        return 1

    try:
        has_pgvector = inspect_pgvector_available(database_url)
    except Exception as exc:
        print(f"Failed to inspect pgvector availability: {exc}", file=sys.stderr)
        return 1

    target_revision = choose_target_revision(has_pgvector)
    if has_pgvector:
        print("pgvector detected on server; running full migration to head.")
    else:
        print(
            "pgvector not available on server; applying migrations through "
            f"{SAFE_FALLBACK_REVISION} only."
        )

    return run_alembic_upgrade(target_revision)


if __name__ == "__main__":
    raise SystemExit(main())
