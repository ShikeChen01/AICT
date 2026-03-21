"""Tests for StripeService — Stripe API interactions (mocked)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, User


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
async def test_create_checkout_session(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-checkout", email="checkout@test.com")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    svc = StripeService(db)
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    with patch("stripe.checkout.Session.create", return_value=mock_session), \
         patch("stripe.Customer.create", return_value=MagicMock(id="cus_new123")):
        url = await svc.create_checkout_session(user, "individual", "https://app.aict.dev/settings/billing")
        assert url == "https://checkout.stripe.com/test"


@pytest.mark.asyncio
async def test_create_portal_session(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-portal", email="portal@test.com", stripe_customer_id="cus_existing")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    svc = StripeService(db)
    mock_session = MagicMock()
    mock_session.url = "https://billing.stripe.com/test"
    with patch("stripe.billing_portal.Session.create", return_value=mock_session):
        url = await svc.create_portal_session(user, "https://app.aict.dev/settings/billing")
        assert url == "https://billing.stripe.com/test"


@pytest.mark.asyncio
async def test_handle_checkout_completed(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-webhook", email="webhook@test.com", stripe_customer_id="cus_wh123")
    db.add(user)
    await db.commit()
    svc = StripeService(db)
    event_data = {
        "customer": "cus_wh123",
        "subscription": "sub_wh123",
        "metadata": {"tier": "individual", "user_id": str(user.id)},
    }
    await svc.handle_checkout_completed(event_data)
    await db.refresh(user)
    assert user.tier == "individual"


@pytest.mark.asyncio
async def test_handle_subscription_deleted(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-cancel", email="cancel@test.com", tier="individual", stripe_customer_id="cus_cancel")
    db.add(user)
    await db.commit()
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_cancel", stripe_subscription_id="sub_cancel")
    db.add(sub)
    await db.commit()
    svc = StripeService(db)
    await svc.handle_subscription_deleted({"customer": "cus_cancel", "id": "sub_cancel"})
    await db.refresh(user)
    assert user.tier == "free"


@pytest.mark.asyncio
async def test_handle_payment_failed(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-fail", email="fail@test.com", tier="individual", stripe_customer_id="cus_fail")
    db.add(user)
    await db.commit()
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_fail", stripe_subscription_id="sub_fail", status="active")
    db.add(sub)
    await db.commit()
    svc = StripeService(db)
    await svc.handle_payment_failed({"customer": "cus_fail", "subscription": "sub_fail"})
    await db.refresh(sub)
    assert sub.status == "past_due"


@pytest.mark.asyncio
async def test_handle_invoice_paid(db):
    from backend.services.stripe_service import StripeService
    user = User(id=uuid.uuid4(), firebase_uid="uid-paid", email="paid@test.com", tier="individual", stripe_customer_id="cus_paid")
    db.add(user)
    await db.commit()
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_paid", stripe_subscription_id="sub_paid", status="past_due")
    db.add(sub)
    await db.commit()
    svc = StripeService(db)
    await svc.handle_invoice_paid({"subscription": "sub_paid"})
    await db.refresh(sub)
    assert sub.status == "active"
