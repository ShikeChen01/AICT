"""
Run Alembic migrations at backend startup.

Simple and direct: always migrates to head.  pgvector is a hard
requirement in all environments.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.config import settings

logger = logging.getLogger(__name__)


def run_startup_migrations() -> None:
    """Upgrade the database to the latest Alembic revision."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    script_location = repo_root / "backend" / "migrations"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(script_location))

    previous_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
