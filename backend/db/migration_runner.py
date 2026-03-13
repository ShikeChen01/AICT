"""
Run database migrations at backend startup.

Uses the shared upgrade wrapper so legacy 024-029 databases can be converged to
the squashed baseline before normal Alembic upgrades continue.
"""

from __future__ import annotations

import os

from backend.config import settings
from backend.scripts.upgrade_db import upgrade_db


def run_startup_migrations() -> None:
    """Upgrade the database to the latest Alembic revision."""
    previous_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        upgrade_db()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
