"""Tests for user API key management endpoints."""
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import User, UserAPIKey
from backend.main import app
from backend.core.auth import get_current_user
from backend.db.session import get_db


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@test.com"
    user.display_name = "Test"
    return user


@pytest.mark.asyncio
async def test_list_api_keys(mock_user):
    mock_key = MagicMock(spec=UserAPIKey)
    mock_key.provider = "anthropic"
    mock_key.display_hint = "...abc"
    mock_key.is_valid = True

    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    with patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        MockRepo.return_value.list_for_user = AsyncMock(return_value=[mock_key])
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/auth/api-keys",
                    headers={"Authorization": "Bearer test"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 1
                assert data[0]["provider"] == "anthropic"
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_upsert_api_key(mock_user):
    mock_key = MagicMock(spec=UserAPIKey)
    mock_key.provider = "anthropic"
    mock_key.display_hint = "...key"
    mock_key.is_valid = True

    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    with patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        MockRepo.return_value.upsert = AsyncMock(return_value=mock_key)
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    "/api/v1/auth/api-keys/anthropic",
                    json={"api_key": "sk-ant-xxx"},
                    headers={"Authorization": "Bearer test"},
                )
                assert resp.status_code == 200
                assert resp.json()["provider"] == "anthropic"
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_upsert_invalid_provider(mock_user):
    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/auth/api-keys/invalid_provider",
                json={"api_key": "sk-xxx"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_delete_api_key(mock_user):
    mock_db = AsyncMock()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    with patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        MockRepo.return_value.delete_key = AsyncMock(return_value=True)
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(
                    "/api/v1/auth/api-keys/anthropic",
                    headers={"Authorization": "Bearer test"},
                )
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
