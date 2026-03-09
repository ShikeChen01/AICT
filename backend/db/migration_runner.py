"""
Run Alembic migrations at backend startup.

Uses safe_migrate logic: if the PostgreSQL server does not have pgvector
installed, migrations stop at revision 024 instead of failing on 025.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.config import settings
from backend.scripts.safe_migrate import (
    choose_target_revision,
    inspect_pgvector_available,
)

logger = logging.getLogger(__name__)


def run_startup_migrations() -> None:
    """
    Upgrade the database to the latest safe Alembic revision.
    """
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "backend" / "alembic.ini"
    script_location = repo_root / "backend" / "migrations"

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(script_location))

    previous_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        try:
            has_pgvector = inspect_pgvector_available(settings.database_url)
        except Exception:
            logger.warning(
                "Could not check pgvector availability; falling back to safe revision"
            )
            has_pgvector = False

        target = choose_target_revision(has_pgvector)
        if not has_pgvector:
            logger.info(
                "pgvector not available; migrating to safe fallback revision (%s)",
                target,
            )
        command.upgrade(config, target)
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
