"""
Upgrade the database to the current Alembic head.

Handles the v3.1 migration squash: if the DB is on a revision from the old
chain (001–029) that no longer exists on disk, we re-stamp to 001_baseline
before running ``upgrade head``.

Usage:
    python -m backend.scripts.upgrade_db
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl as _ssl
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

logger = logging.getLogger(__name__)

# The baseline revision that replaces the entire old 001–029 chain.
_BASELINE_REV = "001_baseline"


def _build_ssl_connect_args() -> dict:
    """Return asyncpg SSL connect_args when DB_SSL_MODE=require."""
    ssl_mode = os.getenv("DB_SSL_MODE", "").lower()
    if ssl_mode == "require":
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        return {"ssl": ctx}
    return {}


async def _restamp_if_orphaned_async(cfg: Config) -> None:
    """Re-stamp the DB to 001_baseline when its current revision is orphaned.

    After squashing old migrations into a single baseline file, the DB's
    ``alembic_version`` still holds the old head (e.g. ``029_merge_…``).
    Alembic cannot build a revision chain from a revision that has no
    corresponding .py file, so ``upgrade head`` crashes.

    This helper detects that situation and re-stamps — a metadata-only
    change that tells Alembic "the DB is at 001_baseline" without running
    any SQL against the actual tables (the schema is already correct).
    """
    script = ScriptDirectory.from_config(cfg)
    known_revisions = {rev.revision for rev in script.walk_revisions()}

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.getenv("DATABASE_URL", "")
    if not url:
        return  # Nothing to check without a URL.

    connect_args = _build_ssl_connect_args()
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        async with engine.connect() as conn:
            # Check whether alembic_version table exists.
            result = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )
            )
            if result.fetchone() is None:
                return  # Fresh DB — alembic upgrade will handle everything.

            row = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            row = row.fetchone()
            if row is None:
                return  # No version stamped yet.

            current_rev = row[0]
            if current_rev in known_revisions:
                return  # Revision chain is intact — nothing to do.

            logger.warning(
                "DB revision %r is not in the current migration chain (squashed). "
                "Re-stamping to %s.",
                current_rev,
                _BASELINE_REV,
            )
            await conn.execute(
                text("UPDATE alembic_version SET version_num = :rev"),
                {"rev": _BASELINE_REV},
            )
            await conn.commit()
    finally:
        await engine.dispose()


def _restamp_if_orphaned(cfg: Config) -> None:
    """Sync wrapper around the async restamp check."""
    asyncio.run(_restamp_if_orphaned_async(cfg))


def upgrade_db() -> None:
    """Run ``alembic upgrade head``."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations.")

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    script_location = repo_root / "backend" / "migrations"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(script_location))

    _restamp_if_orphaned(cfg)
    command.upgrade(cfg, "head")


def main() -> int:
    upgrade_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
