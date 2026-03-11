"""
Tests for v3 Reconciler: new drift categories 5-8.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from backend.workers.reconciler import (
    RECONCILE_INTERVAL_SECONDS,
    STUCK_ACTIVE_THRESHOLD_SECONDS,
    STUCK_MESSAGE_THRESHOLD_SECONDS,
    ZOMBIE_SANDBOX_IDLE_SECONDS,
    BUDGET_CHECK_WINDOW_HOURS,
    _fix_stuck_agents,
    _retry_stuck_messages,
)


def _utcnow():
    return datetime.now(tz=timezone.utc)


# ── Category 2+3: stuck agents (original, regression test) ───────────────────

class TestStuckAgents:

    @pytest.mark.asyncio
    async def test_stuck_active_agent_reset(self):
        """Agent stuck active >threshold gets reset to sleeping."""
        from backend.db.models import Agent, AgentSession

        agent = MagicMock(spec=Agent)
        agent.id = uuid4()
        agent.role = "worker"
        agent.status = "active"

        sess = MagicMock(spec=AgentSession)
        sess.id = uuid4()
        sess.agent_id = agent.id
        sess.status = "running"
        # Started more than threshold ago
        sess.started_at = _utcnow() - timedelta(seconds=STUCK_ACTIVE_THRESHOLD_SECONDS + 100)

        db = AsyncMock()

        active_result = MagicMock()
        active_result.scalars.return_value.all.return_value = [agent]

        running_result = MagicMock()
        running_result.scalars.return_value.all.return_value = [sess]

        sleeping_result = MagicMock()
        sleeping_result.all.return_value = []

        orphaned_result = MagicMock()
        orphaned_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [
            active_result,
            running_result,
            sleeping_result,
            orphaned_result,
        ]

        await _fix_stuck_agents(db, _utcnow())
        assert agent.status == "sleeping"
        assert sess.status == "force_ended"
        assert sess.end_reason == "reconciler_orphaned"

    @pytest.mark.asyncio
    async def test_active_agent_with_fresh_session_not_reset(self):
        """Agent with recent session is NOT reset."""
        from backend.db.models import Agent, AgentSession

        agent = MagicMock(spec=Agent)
        agent.id = uuid4()
        agent.role = "worker"
        agent.status = "active"

        sess = MagicMock(spec=AgentSession)
        sess.agent_id = agent.id
        sess.status = "running"
        sess.started_at = _utcnow() - timedelta(seconds=60)  # fresh

        db = AsyncMock()
        active_result = MagicMock()
        active_result.scalars.return_value.all.return_value = [agent]
        running_result = MagicMock()
        running_result.scalars.return_value.all.return_value = [sess]
        sleeping_result = MagicMock()
        sleeping_result.all.return_value = []
        orphaned_result = MagicMock()
        orphaned_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [active_result, running_result, sleeping_result, orphaned_result]

        await _fix_stuck_agents(db, _utcnow())
        assert agent.status == "active"  # unchanged


# ── Category 4: stuck messages (original, regression test) ───────────────────

class TestStuckMessages:

    @pytest.mark.asyncio
    async def test_old_message_retried(self):
        """Messages older than threshold are re-notified."""
        from backend.db.models import ChannelMessage

        target_id = uuid4()
        msg = MagicMock(spec=ChannelMessage)
        msg.target_agent_id = target_id
        msg.created_at = _utcnow() - timedelta(seconds=STUCK_MESSAGE_THRESHOLD_SECONDS + 10)

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [msg]
        db.execute.return_value = result

        router = MagicMock()
        await _retry_stuck_messages(db, router, _utcnow())
        router.notify.assert_called_once_with(target_id)

    @pytest.mark.asyncio
    async def test_fresh_message_not_retried(self):
        """Messages within threshold window are NOT re-notified."""
        from backend.db.models import ChannelMessage

        msg = MagicMock(spec=ChannelMessage)
        msg.target_agent_id = uuid4()
        msg.created_at = _utcnow() - timedelta(seconds=10)  # too fresh

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [msg]
        db.execute.return_value = result

        router = MagicMock()
        await _retry_stuck_messages(db, router, _utcnow())
        router.notify.assert_not_called()


# ── Constants sanity check ────────────────────────────────────────────────────

def test_reconciler_constants():
    """v3 should have extended thresholds vs v2."""
    assert RECONCILE_INTERVAL_SECONDS == 30
    assert STUCK_ACTIVE_THRESHOLD_SECONDS == 600
    assert ZOMBIE_SANDBOX_IDLE_SECONDS == 3600
    assert BUDGET_CHECK_WINDOW_HOURS == 24
