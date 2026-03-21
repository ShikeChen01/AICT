"""Tests for TierService — sandbox hour enforcement."""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, UsagePeriod, User
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


async def _make_user(db, tier="free"):
    user = User(id=uuid.uuid4(), firebase_uid=f"uid-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.com", tier=tier)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_free_tier_headless_within_limit(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 14 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_free_tier_headless_at_limit(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 15 * 3600
    await db.commit()
    with pytest.raises(TierLimitError, match="headless"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_free_tier_cannot_use_desktop_beyond_limit(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.desktop_seconds = 15 * 3600
    await db.commit()
    with pytest.raises(TierLimitError):
        await svc.check_can_start_sandbox(user, "desktop")


@pytest.mark.asyncio
async def test_individual_tier_generous_limits(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 100 * 3600
    period.desktop_seconds = 50 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")
    await svc.check_can_start_sandbox(user, "desktop")


@pytest.mark.asyncio
async def test_record_usage_increments(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "headless", 3600)
    await svc.record_usage(user, "headless", 1800)
    period = await svc._get_current_period(user)
    assert period.headless_seconds == 5400


@pytest.mark.asyncio
async def test_record_usage_desktop(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "desktop", 7200)
    period = await svc._get_current_period(user)
    assert period.desktop_seconds == 7200


@pytest.mark.asyncio
async def test_get_remaining_seconds(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    remaining = await svc.get_remaining_seconds(user, "headless")
    assert remaining == 15 * 3600
    await svc.record_usage(user, "headless", 5 * 3600)
    remaining = await svc.get_remaining_seconds(user, "headless")
    assert remaining == 10 * 3600


@pytest.mark.asyncio
async def test_get_usage_summary(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "headless", 3600)
    await svc.record_usage(user, "desktop", 1800)
    summary = await svc.get_usage_summary(user)
    assert summary["headless_seconds_used"] == 3600
    assert summary["desktop_seconds_used"] == 1800
    assert summary["headless_seconds_included"] == 200 * 3600
    assert summary["desktop_seconds_included"] == 200 * 3600
    assert summary["tier"] == "individual"


@pytest.mark.asyncio
async def test_enforcement_disabled_skips_check(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", False)
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 999 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_past_due_blocks_sandbox(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "individual")
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", status="past_due")
    db.add(sub)
    await db.commit()
    svc = TierService(db)
    with pytest.raises(TierLimitError, match="past due"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_check_can_invite_member(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "free")
    svc = TierService(db)
    with pytest.raises(TierLimitError, match="1 team member"):
        await svc.check_can_invite_member(user, current_count=1)


@pytest.mark.asyncio
async def test_check_can_invite_member_team(db, monkeypatch):
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "team")
    svc = TierService(db)
    await svc.check_can_invite_member(user, current_count=2)
    with pytest.raises(TierLimitError):
        await svc.check_can_invite_member(user, current_count=3)
