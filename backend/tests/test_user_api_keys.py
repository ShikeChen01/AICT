"""Tests for UserAPIKey model and repository."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, User, UserAPIKey


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_api_key_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-apikey", email="apikey@test.com")
    db.add(user)
    await db.commit()

    key = UserAPIKey(
        id=uuid.uuid4(),
        user_id=user.id,
        provider="anthropic",
        encrypted_key="gAAAAAB...",
        display_hint="...abc",
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    assert key.provider == "anthropic"
    assert key.display_hint == "...abc"
    assert key.is_valid is True


@pytest.mark.asyncio
async def test_user_api_key_unique_per_provider(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-uniq", email="uniq@test.com")
    db.add(user)
    await db.commit()

    key1 = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="anthropic", encrypted_key="k1")
    db.add(key1)
    await db.commit()

    key2 = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="anthropic", encrypted_key="k2")
    db.add(key2)
    with pytest.raises(Exception):
        await db.commit()


@pytest.mark.asyncio
async def test_user_api_key_relationship(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-rel", email="rel@test.com")
    db.add(user)
    await db.commit()

    key = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="openai", encrypted_key="k")
    db.add(key)
    await db.commit()

    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.provider == "openai"
