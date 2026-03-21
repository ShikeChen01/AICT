"""Tests for billing API endpoints."""
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.auth import get_current_user
from backend.db.models import User, Subscription
from backend.db.session import get_db
from backend.main import app


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.tier = "free"
    user.stripe_customer_id = None
    user.email = "test@test.com"
    user.display_name = "Test"
    return user


@pytest.mark.asyncio
async def test_get_subscription_returns_tier(mock_user):
    mock_db = AsyncMock()
    # Simulate no Subscription row — falls back to User.tier
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/billing/subscription", headers={"Authorization": "Bearer test"})
            assert resp.status_code == 200
            assert resp.json()["tier"] == "free"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_usage_returns_summary(mock_user):
    mock_summary = {
        "tier": "free", "period_start": "2026-03-01T00:00:00+00:00",
        "period_end": "2026-04-01T00:00:00+00:00",
        "headless_seconds_used": 3600, "headless_seconds_included": 54000,
        "desktop_seconds_used": 0, "desktop_seconds_included": 54000,
    }
    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    with patch("backend.api.v1.billing.TierService") as MockTier:
        MockTier.return_value.get_usage_summary = AsyncMock(return_value=mock_summary)
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/billing/usage", headers={"Authorization": "Bearer test"})
                assert resp.status_code == 200
                assert resp.json()["headless_seconds_used"] == 3600
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_checkout_requires_valid_tier(mock_user):
    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/billing/checkout-session", json={"tier": "invalid"}, headers={"Authorization": "Bearer test"})
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature():
    with patch("backend.api.v1.billing.settings") as mock_settings:
        mock_settings.stripe_webhook_secret = "whsec_test"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/billing/webhook", content=b'{}', headers={"stripe-signature": "bad_sig"})
            assert resp.status_code == 400
