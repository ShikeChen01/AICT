"""Unit tests for WorkerManager (start/stop, interrupt)."""

import os
from uuid import uuid4

import pytest

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
