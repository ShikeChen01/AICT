"""Regression tests for AgentWorker failure recovery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from backend.workers.agent_worker import AgentWorker


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDbSession:
    def __init__(self, agent, project):
        self._agent = agent
        self._project = project
        self._execute_count = 0
        self.rollback_called = False
        self.commit_count = 0

    async def execute(self, _query):
        self._execute_count += 1
        if self._execute_count % 2 == 1:
            return _ScalarOneOrNoneResult(self._agent)
        return _ScalarOneOrNoneResult(self._project)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_called = True


class _SessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_agent_worker_recovers_from_cycle_failure(monkeypatch) -> None:
    """A single wake-cycle failure should not terminate the outer worker loop."""
    agent_id = uuid4()
    project_id = uuid4()
    agent = SimpleNamespace(id=agent_id, project_id=project_id, role="engineer", status="sleeping")
    project = SimpleNamespace(id=project_id)
    db = _FakeDbSession(agent, project)
    end_session_error = AsyncMock()

    monkeypatch.setattr(
        "backend.workers.agent_worker.AsyncSessionLocal",
        lambda: _SessionContext(db),
    )
    monkeypatch.setattr(
        "backend.workers.agent_worker.SessionService",
        lambda _db: SimpleNamespace(
            create_session=AsyncMock(return_value=SimpleNamespace(id=uuid4(), iteration_count=0)),
            end_session_error=end_session_error,
        ),
    )
    monkeypatch.setattr(
        "backend.agents.agent.Agent.run",
        AsyncMock(side_effect=RuntimeError("cycle failed")),
    )

    worker = AgentWorker(agent_id, project_id)
    run_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)

    worker._queue.put_nowait(None)
    for _ in range(10):
        await asyncio.sleep(0)

    assert db.rollback_called is True
    end_session_error.assert_awaited_once()
    assert agent.status == "sleeping"
    assert run_task.done() is False

    run_task.cancel()
    await run_task
