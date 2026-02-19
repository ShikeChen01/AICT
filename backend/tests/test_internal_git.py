"""Tests for internal git endpoint error handling."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import verify_agent_request
from backend.db.session import get_db
from backend.main import app


@pytest.fixture
async def internal_api_client(session: AsyncSession):
    """Create an API client bound to the test database session."""

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_branches_returns_400_for_non_git_repo(
    internal_api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def override_verify_agent_request() -> str:
        return str(uuid.uuid4())

    monkeypatch.setattr(settings, "code_repo_path", str(tmp_path))
    app.dependency_overrides[verify_agent_request] = override_verify_agent_request
    try:
        response = await internal_api_client.get("/internal/agent/git/branches")
    finally:
        app.dependency_overrides.pop(verify_agent_request, None)

    assert response.status_code == 400
    assert response.json()["detail"]
