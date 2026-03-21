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


# ── Repository tests ──────────────────────────────────────────────────

from backend.db.repositories.user_api_keys import UserAPIKeyRepository


@pytest.mark.asyncio
async def test_repo_upsert_creates_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo1", email="repo1@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    key = await repo.upsert(user.id, "anthropic", "sk-ant-api03-real-key-here")
    assert key.provider == "anthropic"
    assert key.display_hint == "...ere"  # "..." prefix + last 3 chars
    assert key.encrypted_key != "sk-ant-api03-real-key-here"  # encrypted


@pytest.mark.asyncio
async def test_repo_upsert_updates_existing(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo2", email="repo2@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-old-key")
    updated = await repo.upsert(user.id, "anthropic", "sk-new-key")
    assert updated.display_hint == "...key"  # "..." prefix + last 3 of new key


@pytest.mark.asyncio
async def test_repo_get_decrypted_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo3", email="repo3@test.com")
    db.add(user)
    await db.commit()

    enc_key = "test-key-32-chars-padded-ok!!!!!"
    repo = UserAPIKeyRepository(db, encryption_key=enc_key)
    await repo.upsert(user.id, "openai", "sk-openai-secret-123")

    plaintext = await repo.get_decrypted_key(user.id, "openai")
    assert plaintext == "sk-openai-secret-123"


@pytest.mark.asyncio
async def test_repo_get_decrypted_key_missing(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo4", email="repo4@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    plaintext = await repo.get_decrypted_key(user.id, "anthropic")
    assert plaintext is None


@pytest.mark.asyncio
async def test_repo_list_for_user(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo5", email="repo5@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-ant-xxx")
    await repo.upsert(user.id, "openai", "sk-oai-xxx")

    keys = await repo.list_for_user(user.id)
    providers = {k.provider for k in keys}
    assert providers == {"anthropic", "openai"}


@pytest.mark.asyncio
async def test_repo_delete_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo6", email="repo6@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-ant-xxx")
    deleted = await repo.delete_key(user.id, "anthropic")
    assert deleted is True

    keys = await repo.list_for_user(user.id)
    assert len(keys) == 0


@pytest.mark.asyncio
async def test_repo_delete_nonexistent(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo7", email="repo7@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    deleted = await repo.delete_key(user.id, "anthropic")
    assert deleted is False
