"""
Unit tests for the reconciler module.

All tests are offline (no real DB).  They verify:
- _repair_dangling_tool_use does correct injection  (covered by test_prompt_assembly)
- Orphan agent detection calls ensure_workers_for_all_agents
- Stuck-active agent gets reset to sleeping
- Orphaned running sessions get force-ended
- Stuck "sent" messages trigger notify
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.workers.reconciler import (
    _fix_stuck_agents,
    _retry_stuck_messages,
    _reconcile_once,
    STUCK_ACTIVE_THRESHOLD_SECONDS,
    STUCK_MESSAGE_THRESHOLD_SECONDS,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    """Minimal async DB session stub."""

    def __init__(self, execute_map=None):
        self._execute_map = execute_map or {}
        self._call_index = 0
        self.committed = False
        self.rolled_back = False
        self._calls = []

    def _next_result(self, query_key=None):
        key = query_key or self._call_index
        self._call_index += 1
        return self._execute_map.get(key, _ScalarResult([]))

    async def execute(self, query):
        result = self._next_result()
        return result

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Tests: _reconcile_once — orphan agents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconcile_once_calls_ensure_workers(monkeypatch):
    """_reconcile_once should call ensure_workers_for_all_agents on the wm."""
    import backend.workers.reconciler as rec_mod

    mock_wm = MagicMock()
    mock_wm.ensure_workers_for_all_agents = AsyncMock(return_value=[])
    mock_router = MagicMock()

    monkeypatch.setattr(rec_mod, "get_worker_manager", lambda: mock_wm)
    monkeypatch.setattr(rec_mod, "get_message_router", lambda: mock_router)

    fake_db_ctx = MagicMock()
    fake_db = _FakeDB(execute_map={
        0: _ScalarResult([]),  # active agents
        1: _ScalarResult([]),  # sleeping agents (all() returns row-tuples)
        2: _ScalarResult([]),  # stuck messages
    })
    fake_db_ctx.__aenter__ = AsyncMock(return_value=fake_db)
    fake_db_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(rec_mod, "AsyncSessionLocal", lambda: fake_db_ctx)

    await _reconcile_once()

    mock_wm.ensure_workers_for_all_agents.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_once_logs_spawned_agents(monkeypatch, caplog):
    """When orphan agents are found, their IDs are logged."""
    import backend.workers.reconciler as rec_mod

    orphan_id = uuid4()
    mock_wm = MagicMock()
    mock_wm.ensure_workers_for_all_agents = AsyncMock(return_value=[orphan_id])
    mock_router = MagicMock()

    monkeypatch.setattr(rec_mod, "get_worker_manager", lambda: mock_wm)
    monkeypatch.setattr(rec_mod, "get_message_router", lambda: mock_router)

    fake_db_ctx = MagicMock()
    fake_db = _FakeDB(execute_map={
        0: _ScalarResult([]),
        1: _ScalarResult([]),
        2: _ScalarResult([]),
    })
    fake_db_ctx.__aenter__ = AsyncMock(return_value=fake_db)
    fake_db_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(rec_mod, "AsyncSessionLocal", lambda: fake_db_ctx)

    import logging
    with caplog.at_level(logging.INFO, logger="backend.workers.reconciler"):
        await _reconcile_once()

    assert any("orphan" in r.message.lower() or "spawn" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: _fix_stuck_agents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fix_stuck_agents_resets_active_with_no_session():
    """Active agent with no running session gets reset to sleeping."""
    now = _utcnow()
    agent = SimpleNamespace(
        id=uuid4(), role="manager", status="active",
    )

    call_count = 0
    async def _fake_execute(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ScalarResult([agent])   # active agents
        if call_count == 2:
            return _ScalarResult([])        # running sessions for that agent
        return _ScalarResult([])            # sleeping agents

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    await _fix_stuck_agents(db, now)

    assert agent.status == "sleeping"


@pytest.mark.asyncio
async def test_fix_stuck_agents_resets_agent_with_old_session():
    """Active agent whose session started > threshold ago gets reset."""
    now = _utcnow()
    old_start = now - timedelta(seconds=STUCK_ACTIVE_THRESHOLD_SECONDS + 60)
    agent_id = uuid4()
    agent = SimpleNamespace(id=agent_id, role="manager", status="active")
    sess = SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        status="running",
        started_at=old_start,
        ended_at=None,
    )

    call_count = 0
    async def _fake_execute(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ScalarResult([agent])
        if call_count == 2:
            return _ScalarResult([sess])
        return _ScalarResult([])

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    await _fix_stuck_agents(db, now)

    assert agent.status == "sleeping"
    assert sess.status == "force_ended"
    assert sess.end_reason == "reconciler_orphaned"


@pytest.mark.asyncio
async def test_fix_stuck_agents_skips_recently_active_session():
    """Active agent with a recent session is NOT reset."""
    now = _utcnow()
    recent_start = now - timedelta(seconds=30)
    agent_id = uuid4()
    agent = SimpleNamespace(id=agent_id, role="manager", status="active")
    sess = SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        status="running",
        started_at=recent_start,
        ended_at=None,
    )

    call_count = 0
    async def _fake_execute(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ScalarResult([agent])
        if call_count == 2:
            return _ScalarResult([sess])
        return _ScalarResult([])

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    await _fix_stuck_agents(db, now)

    assert agent.status == "active"   # not changed
    assert sess.status == "running"   # not changed


@pytest.mark.asyncio
async def test_fix_stuck_agents_force_ends_sleeping_agent_running_session():
    """Running session for a sleeping agent is force-ended."""
    now = _utcnow()
    agent_id = uuid4()
    sess = SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        status="running",
        ended_at=None,
    )

    # _fix_stuck_agents calls db.execute three times:
    # 1. select(Agent) where status=active  -> scalars().all() -> []
    # 2. select(Agent.id) where status=sleeping -> .all() -> [(agent_id,)]
    # 3. select(AgentSession) where agent_id in sleeping_ids, status=running
    #    -> scalars().all() -> [sess]

    class _TupleResult:
        """Mimics a SQLAlchemy result where .all() returns row-tuples."""
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return self._rows

    call_count = 0
    async def _fake_execute(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ScalarResult([])              # no active agents
        if call_count == 2:
            return _TupleResult([(agent_id,)])    # sleeping agent IDs
        if call_count == 3:
            return _ScalarResult([sess])          # orphaned sessions
        return _ScalarResult([])

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    await _fix_stuck_agents(db, now)

    assert sess.status == "force_ended"
    assert sess.end_reason == "reconciler_orphaned"


# ---------------------------------------------------------------------------
# Tests: _retry_stuck_messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_stuck_messages_notifies_old_messages():
    """Messages older than threshold trigger notify."""
    now = _utcnow()
    agent_id = uuid4()
    old_time = now - timedelta(seconds=STUCK_MESSAGE_THRESHOLD_SECONDS + 30)
    msg = SimpleNamespace(
        id=uuid4(),
        target_agent_id=agent_id,
        status="sent",
        created_at=old_time,
    )

    async def _fake_execute(query):
        return _ScalarResult([msg])

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    router = MagicMock()

    await _retry_stuck_messages(db, router, now)

    router.notify.assert_called_once_with(agent_id)


@pytest.mark.asyncio
async def test_retry_stuck_messages_skips_recent_messages():
    """Messages newer than threshold are NOT re-notified."""
    now = _utcnow()
    agent_id = uuid4()
    recent_time = now - timedelta(seconds=5)
    msg = SimpleNamespace(
        id=uuid4(),
        target_agent_id=agent_id,
        status="sent",
        created_at=recent_time,
    )

    async def _fake_execute(query):
        return _ScalarResult([msg])

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()

    router = MagicMock()

    await _retry_stuck_messages(db, router, now)

    router.notify.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: run_reconciler_forever cancellation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_reconciler_forever_stops_on_cancel(monkeypatch):
    """CancelledError from sleep propagates cleanly."""
    from backend.workers.reconciler import run_reconciler_forever

    monkeypatch.setattr("backend.workers.reconciler.RECONCILE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("backend.workers.reconciler._reconcile_once", AsyncMock(side_effect=asyncio.CancelledError))

    task = asyncio.create_task(run_reconciler_forever())
    await asyncio.sleep(0.05)
    with pytest.raises(asyncio.CancelledError):
        await task
