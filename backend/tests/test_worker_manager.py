"""Unit tests for WorkerManager (start/stop, interrupt)."""

import asyncio
import os
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock

from backend.workers.worker_manager import WorkerManager, get_worker_manager
from backend.workers.message_router import reset_message_router


@pytest.fixture
def manager():
    """Fresh WorkerManager (resets singleton state)."""
    m = WorkerManager()
    yield m
    reset_message_router()


@pytest.mark.asyncio
async def test_interrupt_agent_no_worker(manager) -> None:
    """interrupt_agent on unknown agent is no-op."""
    manager.interrupt_agent(uuid4())


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("INTEGRATION_TEST") != "1",
    reason="WorkerManager.start() uses app DB; run with INTEGRATION_TEST=1",
)
@pytest.mark.asyncio
async def test_start_stop_empty_db(manager) -> None:
    """With no agents in DB, start spawns no workers and stop is no-op."""
    await manager.start()
    assert len(manager._workers) == 0
    assert len(manager._tasks) == 0
    await manager.stop()
    assert len(manager._tasks) == 0


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("INTEGRATION_TEST") != "1",
    reason="WorkerManager.start() uses app DB; run with INTEGRATION_TEST=1",
)
@pytest.mark.asyncio
async def test_start_then_stop_cleans_tasks(manager) -> None:
    """Start then stop clears tasks and workers."""
    await manager.start()
    await manager.stop()
    assert len(manager._tasks) == 0
    assert len(manager._workers) == 0


@pytest.mark.asyncio
async def test_worker_done_callback_respawns_on_crash(manager) -> None:
    """Unexpected worker crash schedules a respawn."""
    agent_id = uuid4()
    project_id = uuid4()
    replacement = type(
        "WorkerStub",
        (),
        {"agent_id": agent_id, "project_id": project_id},
    )()

    respawn = AsyncMock()
    manager._spawn_tracked_worker = respawn

    async def _crash():
        raise RuntimeError("boom")

    task = asyncio.create_task(_crash())
    manager._track_worker(replacement, task)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    respawn.assert_called_once_with(agent_id, project_id)


@pytest.mark.asyncio
async def test_worker_done_callback_does_not_respawn_while_shutting_down(manager) -> None:
    """Manager shutdown suppresses respawn for completed worker tasks."""
    manager._shutting_down = True
    agent_id = uuid4()
    project_id = uuid4()
    replacement = type(
        "WorkerStub",
        (),
        {"agent_id": agent_id, "project_id": project_id},
    )()

    respawn = AsyncMock()
    manager._spawn_tracked_worker = respawn

    async def _done():
        return None

    task = asyncio.create_task(_done())
    manager._track_worker(replacement, task)
    await asyncio.sleep(0)

    respawn.assert_not_awaited()
