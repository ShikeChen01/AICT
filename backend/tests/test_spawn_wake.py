"""Tests for spawn_engineer waking the new worker and worker ready signaling."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.workers.agent_worker import AgentWorker
from backend.workers.message_router import MessageRouter, reset_message_router


@pytest.fixture(autouse=True)
def _reset_router():
    yield
    reset_message_router()


class TestAgentWorkerReady:
    """The worker must signal readiness after registering its queue."""

    @pytest.mark.asyncio
    async def test_wait_ready_resolves_after_run_starts(self):
        worker = AgentWorker(uuid4(), uuid4())
        task = asyncio.create_task(worker.run())
        await worker.wait_ready()
        assert worker._ready.is_set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_wait_ready_times_out_if_run_not_called(self):
        worker = AgentWorker(uuid4(), uuid4())
        with pytest.raises(asyncio.TimeoutError):
            await worker.wait_ready(timeout=0.05)


class TestSpawnEngineerWake:
    """spawn_engineer tool must wake the new engineer after spawning."""

    @pytest.mark.asyncio
    async def test_spawn_engineer_sends_wake_signal(self, session, sample_project, monkeypatch):
        from backend.tools.loop_registry import _run_spawn_engineer, RunContext
        from backend.services.agent_service import AgentService

        agent_service = AgentService(session)

        mock_router = MagicMock()
        monkeypatch.setattr(
            "backend.workers.message_router.get_message_router",
            lambda: mock_router,
        )

        mock_wm = MagicMock()
        mock_wm.spawn_worker = AsyncMock()
        monkeypatch.setattr(
            "backend.workers.worker_manager.get_worker_manager",
            lambda: mock_wm,
        )

        spawned_engineer = SimpleNamespace(
            id=uuid4(),
            project_id=sample_project.id,
            display_name="Eng-Test",
            role="engineer",
        )
        monkeypatch.setattr(
            agent_service,
            "spawn_engineer",
            AsyncMock(return_value=spawned_engineer),
        )

        ctx = RunContext(
            db=session,
            agent=SimpleNamespace(id=uuid4(), role="manager", project_id=sample_project.id),
            project=sample_project,
            session_id=uuid4(),
            message_service=MagicMock(),
            session_service=MagicMock(),
            task_service=MagicMock(),
            agent_service=agent_service,
            agent_msg_repo=MagicMock(),
            emit_agent_message=None,
        )

        result = await _run_spawn_engineer(ctx, {"display_name": "Eng-Test"})

        mock_wm.spawn_worker.assert_awaited_once_with(
            spawned_engineer.id, spawned_engineer.project_id
        )
        mock_router.notify.assert_called_once_with(spawned_engineer.id)
        assert str(spawned_engineer.id) in result


class TestWorkerManagerSpawnWaitsReady:
    """WorkerManager.spawn_worker should wait for the worker's queue registration."""

    @pytest.mark.asyncio
    async def test_spawn_worker_waits_for_ready(self):
        from backend.workers.worker_manager import WorkerManager

        wm = WorkerManager()
        agent_id = uuid4()
        project_id = uuid4()

        await wm.spawn_worker(agent_id, project_id)

        worker = next(w for w in wm._workers if w.agent_id == agent_id)
        assert worker._ready.is_set()

        await wm.stop()

    @pytest.mark.asyncio
    async def test_spawn_worker_skips_duplicate(self):
        from backend.workers.worker_manager import WorkerManager

        wm = WorkerManager()
        agent_id = uuid4()
        project_id = uuid4()

        await wm.spawn_worker(agent_id, project_id)
        initial_count = len(wm._workers)
        await wm.spawn_worker(agent_id, project_id)
        assert len(wm._workers) == initial_count

        await wm.stop()
