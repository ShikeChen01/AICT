"""
Upgrade the database to the current Alembic head.

Usage:
    python -m backend.scripts.upgrade_db
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


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
    command.upgrade(cfg, "head")


def main() -> int:
    upgrade_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
