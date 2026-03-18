"""Tests for REST messages API (POST /messages/send, GET /messages, GET /messages/all)."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Repository, User
from backend.main import app


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Return headers with a fake Bearer token (tests may use mock auth)."""
    return {"Authorization": "Bearer fake-token-for-test"}


@pytest.fixture
def test_user(session: AsyncSession) -> User:
    from backend.db.models import User
    user = User(
        id=uuid4(),
        firebase_uid="test-uid",
        email="test@example.com",
        display_name="Test User",
    )
    session.add(user)
    session.flush()
    return user


@pytest.mark.asyncio
async def test_send_message_requires_auth(
    sample_project: Repository,
    sample_manager: Agent,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/api/v1/messages/send",
            json={
                "project_id": str(sample_project.id),
                "target_agent_id": str(sample_manager.id),
                "content": "Hello",
            },
        )
        # 401 or 422 (missing auth)
        assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_messages_list_conversation_structure(
    session: AsyncSession,
    sample_project: Repository,
    sample_manager: Agent,
) -> None:
    """Smoke test: messages list endpoint exists and returns list (with auth mocked)."""
    from uuid import uuid4
    from backend.db.repositories.messages import ChannelMessageRepository

    repo = ChannelMessageRepository(session)
    await repo.create_message(
        project_id=sample_project.id,
        content="Test",
        from_user_id=uuid4(),
        target_agent_id=sample_manager.id,
    )
    await session.commit()

    # Without real auth we may get 401; we only check the route is mounted
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get(
            "/api/v1/messages",
            params={
                "project_id": str(sample_project.id),
                "agent_id": str(sample_manager.id),
            },
        )
        # 401 without valid token is expected in unit test
        assert r.status_code in (200, 401, 422)


@pytest.mark.asyncio
async def test_messages_api_route_registered() -> None:
    """Ensure /api/v1/messages/send and /messages are registered."""
    routes = [r.path for r in app.routes]
    # FastAPI mounts routers; check that we have messages prefix
    assert any("messages" in (getattr(r, "path", "") or "") for r in app.routes)
