"""
Async database session management.
"""

from collections.abc import AsyncGenerator
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings


def _resolve_database_url() -> str:
    """
    Build the database URL.

    When DB_USER / DB_PASSWORD / DB_NAME / DB_SOCKET_PATH env vars are set
    (Cloud Run deployments), assemble the URL from components so passwords
    with special characters don't get mangled by shell/YAML escaping.
    Falls back to DATABASE_URL otherwise (local dev, .env files).
    """
    if settings.db_user and settings.db_password and settings.db_name and settings.db_socket_path:
        pw = quote_plus(settings.db_password)
        return (
            f"postgresql+asyncpg://{settings.db_user}:{pw}"
            f"@/{settings.db_name}?host={settings.db_socket_path}"
        )
    return settings.database_url


engine = create_async_engine(
    _resolve_database_url(),
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
