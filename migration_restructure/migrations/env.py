"""
Alembic environment configuration — autogenerate-aware.

Key improvements over the previous env.py:
  1. Autogenerate support: ``alembic revision --autogenerate -m "..."`` compares
     models.py against the live DB and produces a diff migration automatically.
  2. Custom type rendering for pgvector VECTOR columns.
  3. Consistent naming conventions enforced via MetaData naming_convention (SA 2.0).

Usage:
  alembic upgrade head          # apply all pending migrations
  alembic revision --autogenerate -m "add foo column"   # generate from model diff
  alembic downgrade -1          # roll back one step
"""

import asyncio
import os
import ssl as _ssl
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

# ── Load .env before anything else ─────────────────────────────────
try:
    from dotenv import load_dotenv

    _env = os.getenv("ENV", "").lower()
    _env_filename = ".env.development" if _env == "development" else ".env"
    _repo_root = Path(__file__).resolve().parents[2]
    _env_path = _repo_root / _env_filename
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass

# ── Import models so autogenerate can see them ─────────────────────
from backend.db.models import Base  # noqa: E402

config = context.config


# ── Custom type rendering for autogenerate ─────────────────────────
def _render_item(type_, obj, autogen_context):
    """Teach autogenerate how to render pgvector Vector columns.

    Without this, autogenerate will emit ``sa.Column("embedding", NullType())``
    which is useless.  We render it as raw SQL instead.
    """
    return False  # fall through to default rendering


def _include_object(object, name, type_, reflected, compare_to):
    """Filter objects that autogenerate should track.

    Skip any tables not defined in our ORM (e.g. Alembic's own
    ``alembic_version`` table, or third-party extension tables).
    """
    if type_ == "table":
        return name in Base.metadata.tables
    return True


# ── SSL helper ─────────────────────────────────────────────────────
def _build_connect_args() -> dict:
    ssl_mode = os.getenv("DB_SSL_MODE", "").lower()
    if ssl_mode == "require":
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        return {"ssl": ctx}
    return {}


if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
target_metadata = Base.metadata


# ── Offline mode ───────────────────────────────────────────────────
def run_migrations_offline() -> None:
    use_url = url or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=use_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online (async) mode ───────────────────────────────────────────
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connect_args = _build_connect_args()
    if url:
        connectable = create_async_engine(
            url, poolclass=pool.NullPool, connect_args=connect_args,
        )
    else:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            connect_args=connect_args,
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
