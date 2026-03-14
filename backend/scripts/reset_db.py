"""
Nuke and rebuild the dev database from scratch.

Drops ALL tables (+ the pgvector extension), runs alembic upgrade head,
then optionally re-seeds with the default project/agents.

Usage:
    python -m backend.scripts.reset_db          # reset + seed
    python -m backend.scripts.reset_db --no-seed  # reset only

Safety: refuses to run unless ENV is explicitly 'development' or 'test'.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ALLOWED_ENVS = {"development", "test"}


def build_sync_url(async_url: str) -> str:
    """Convert an asyncpg URL into a sync psycopg2 URL."""
    sync_url = make_url(async_url).set(drivername="postgresql+psycopg2")
    query = dict(sync_url.query)
    if os.getenv("DB_SSL_MODE", "").lower() == "require":
        query.setdefault("sslmode", "require")
    return sync_url.set(query=query).render_as_string(hide_password=False)


def nuke_database(sync_url: str) -> None:
    """Drop every table, extension, and enum in the public schema."""
    engine = create_engine(sync_url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            # Drop all tables (CASCADE handles FKs)
            conn.execute(text(
                "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
            ))
            # Restore default grants
            conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            print("Dropped all objects in public schema.")
    finally:
        engine.dispose()


def run_alembic_upgrade() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    script_location = repo_root / "backend" / "migrations"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(script_location))
    command.upgrade(cfg, "head")
    print("Alembic upgrade to head complete.")


async def run_seed() -> None:
    from backend.scripts.seed import seed
    await seed()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset dev database to a clean state")
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding after reset",
    )
    args = parser.parse_args()

    env = os.getenv("ENV", "").lower()
    if env not in ALLOWED_ENVS:
        print(f"REFUSED: ENV={env!r} is not in {ALLOWED_ENVS}. "
              "Set ENV=development to proceed.")
        return 1

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    sync_url = build_sync_url(database_url)

    print(f"Resetting database (ENV={env}) ...")
    nuke_database(sync_url)
    run_alembic_upgrade()

    if not args.no_seed:
        print("Seeding ...")
        asyncio.run(run_seed())

    print("Done. Fresh database ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
