"""
Upgrade the database to the current Alembic head.

Handles the v3.1 migration squash: if the DB is on a revision from the old
chain (001–029) that no longer exists on disk, we re-stamp to 001_baseline
before running ``upgrade head``.

Usage:
    python -m backend.scripts.upgrade_db
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

logger = logging.getLogger(__name__)

# The baseline revision that replaces the entire old 001–029 chain.
_BASELINE_REV = "001_baseline"


def _restamp_if_orphaned(cfg: Config) -> None:
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

    # Read + update via a disposable sync engine (avoids triggering the async
    # env.py path that command.stamp would use).
    from sqlalchemy import create_engine, text

    url = os.getenv("DATABASE_URL", "")
    sync_url = url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            if not engine.dialect.has_table(conn, "alembic_version"):
                return  # Fresh DB — alembic upgrade will handle everything.
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
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
            conn.execute(
                text("UPDATE alembic_version SET version_num = :rev"),
                {"rev": _BASELINE_REV},
            )
            conn.commit()
    finally:
        engine.dispose()


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
