"""Tests for internal messaging API hardening."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.models import Agent, Repository
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
async def test_send_message_invalid_authenticated_agent_uuid_returns_401(
    internal_api_client: AsyncClient,
    sample_project: Repository,
    sample_manager: Agent,
    sample_engineer: Agent,
) -> None:
    async def override_verify_agent_request() -> str:
        return "not-a-uuid"

    app.dependency_overrides[verify_agent_request] = override_verify_agent_request
    try:
        response = await internal_api_client.post(
            "/internal/agent/send-message",
            json={
                "from_agent_id": str(sample_manager.id),
                "target_agent_id": str(sample_engineer.id),
                "project_id": str(sample_project.id),
                "content": "ping",
            },
        )
    finally:
        app.dependency_overrides.pop(verify_agent_request, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid X-Agent-ID header"
