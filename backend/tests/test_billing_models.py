"""Tests for billing data models."""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, UsagePeriod, User


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
async def test_user_has_tier_field(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="test-uid", email="test@example.com")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.tier == "free"
    assert user.stripe_customer_id is None


@pytest.mark.asyncio
async def test_subscription_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-sub", email="sub@test.com")
    db.add(user)
    await db.commit()
    sub = Subscription(
        id=uuid.uuid4(), user_id=user.id, tier="individual", status="active",
        stripe_customer_id="cus_test123", stripe_subscription_id="sub_test123",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    assert sub.tier == "individual"
    assert sub.status == "active"
    assert sub.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_usage_period_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-usage", email="usage@test.com")
    db.add(user)
    await db.commit()
    period = UsagePeriod(
        id=uuid.uuid4(), user_id=user.id,
        period_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 3, 31, tzinfo=timezone.utc),
        headless_seconds=3600, desktop_seconds=1800,
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)
    assert period.headless_seconds == 3600
    assert period.desktop_seconds == 1800


@pytest.mark.asyncio
async def test_subscription_user_relationship(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-rel", email="rel@test.com")
    db.add(user)
    await db.commit()
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="team")
    db.add(sub)
    await db.commit()
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.tier == "team"
