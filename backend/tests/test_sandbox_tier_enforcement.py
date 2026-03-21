"""Tests for tier enforcement in sandbox creation flow."""
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, User, UsagePeriod
from backend.core.exceptions import TierLimitError


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
async def test_sandbox_creation_blocked_when_over_limit(db, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    from backend.services.tier_service import TierService
    user = User(id=uuid.uuid4(), firebase_uid="uid-block", email="block@test.com", tier="free")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    svc = TierService(db)
    await svc.record_usage(user, "headless", 15 * 3600)
    with pytest.raises(TierLimitError, match="headless"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_sandbox_creation_allowed_within_limit(db, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    from backend.services.tier_service import TierService
    user = User(id=uuid.uuid4(), firebase_uid="uid-ok", email="ok@test.com", tier="individual")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    svc = TierService(db)
    await svc.record_usage(user, "headless", 50 * 3600)
    await svc.check_can_start_sandbox(user, "headless")
