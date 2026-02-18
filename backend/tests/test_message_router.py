"""Unit tests for MessageRouter (singleton, notify, replay)."""

import asyncio
from uuid import uuid4

import pytest

from backend.db.models import ChannelMessage
from backend.workers.message_router import (
    MessageRouter,
    get_message_router,
    reset_message_router,
)


@pytest.fixture(autouse=True)
def _reset_router():
    """Reset singleton after each test to avoid cross-test leakage."""
    yield
    reset_message_router()


@pytest.mark.asyncio
async def test_notify_puts_sentinel_in_queue() -> None:
    router = get_message_router()
    agent_id = uuid4()
    q: asyncio.Queue = asyncio.Queue()
    router.register(agent_id, q)

    router.notify(agent_id)
    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert item is None  # Sentinel: no payload


@pytest.mark.asyncio
async def test_notify_unknown_agent_no_op() -> None:
    router = get_message_router()
    router.notify(uuid4())  # No queue registered, should not raise


@pytest.mark.asyncio
async def test_unregister_removes_queue() -> None:
    router = get_message_router()
    agent_id = uuid4()
    q: asyncio.Queue = asyncio.Queue()
    router.register(agent_id, q)
    router.unregister(agent_id)
    router.notify(agent_id)  # No-op, no exception
    assert q.empty()


@pytest.mark.asyncio
async def test_replay_notifies_per_target(
    sample_project,
    sample_manager,
    sample_engineer,
    session,
) -> None:
    from backend.db.models import ChannelMessage, Repository
    from backend.db.repositories.messages import ChannelMessageRepository

    repo = ChannelMessageRepository(session)
    msg1 = await repo.create_message(
        project_id=sample_project.id,
        content="To manager",
        from_agent_id=uuid4(),  # user or other agent
        target_agent_id=sample_manager.id,
    )
    msg2 = await repo.create_message(
        project_id=sample_project.id,
        content="To engineer",
        from_agent_id=uuid4(),
        target_agent_id=sample_engineer.id,
    )
    await session.commit()

    router = get_message_router()
    q_manager: asyncio.Queue = asyncio.Queue()
    q_engineer: asyncio.Queue = asyncio.Queue()
    router.register(sample_manager.id, q_manager)
    router.register(sample_engineer.id, q_engineer)

    await router.replay([msg1, msg2])

    # Each target should have received one notify
    m = await asyncio.wait_for(q_manager.get(), timeout=1.0)
    assert m is None
    e = await asyncio.wait_for(q_engineer.get(), timeout=1.0)
    assert e is None
