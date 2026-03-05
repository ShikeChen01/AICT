"""
Alembic environment configuration.

When run from the CLI (``alembic upgrade head``), the .env file is not loaded
automatically — only pydantic_settings does that at app startup.  We use
dotenv here so that DATABASE_URL is always available regardless of how
Alembic is invoked.
"""

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

# Load the correct .env file before anything else so DATABASE_URL is set.
# Mirrors the logic in backend/config.py: ENV=development → .env.development,
# otherwise .env.
try:
    from dotenv import load_dotenv

    _env = os.getenv("ENV", "").lower()
    _env_filename = ".env.development" if _env == "development" else ".env"
    # Walk up from backend/migrations/ to the repo root to find the .env file
    _repo_root = Path(__file__).resolve().parents[2]
    _env_path = _repo_root / _env_filename
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on OS env vars

from backend.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer DATABASE_URL env (avoids ConfigParser % interpolation); fallback to alembic.ini
url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    use_url = url or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=use_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    if url:
        connectable = create_async_engine(url, poolclass=pool.NullPool)
    else:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
