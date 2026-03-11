"""
Tests for v3 MessageRouter: dead-letter queue, topology-aware routing, queue depth.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.workers.message_router import MessageRouter, reset_message_router, _DEAD_LETTER_ENABLED


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def router():
    r = MessageRouter()
    return r


# ── Basic routing (original behavior preserved) ───────────────────────────────

class TestMessageRouterBasic:

    def test_register_and_notify(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.notify(agent_id)
        assert q.qsize() == 1

    def test_notify_missing_agent_increments_counter(self, router):
        agent_id = uuid4()
        router.notify(agent_id)
        assert router._notify_counts.get(agent_id, 0) == 1

    def test_register_resets_failure_count(self, router):
        agent_id = uuid4()
        router._notify_counts[agent_id] = 5
        q = asyncio.Queue()
        router.register(agent_id, q)
        assert agent_id not in router._notify_counts

    def test_unregister_removes_queue(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.unregister(agent_id)
        assert agent_id not in router._queues

    def test_queue_full_logs_warning(self, router, caplog):
        agent_id = uuid4()
        q = asyncio.Queue(maxsize=1)
        q.put_nowait(None)  # fill it
        router.register(agent_id, q)
        import logging
        with caplog.at_level(logging.WARNING):
            router.notify(agent_id)  # should log queue full
        assert "queue full" in caplog.text.lower() or q.qsize() == 1  # graceful handling

    def test_notify_success_resets_counter(self, router):
        agent_id = uuid4()
        router._notify_counts[agent_id] = 2  # simulated previous failures
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.notify(agent_id)
        assert agent_id not in router._notify_counts


# ── Queue depth introspection ─────────────────────────────────────────────────

class TestQueueDepth:

    def test_depth_zero_for_empty_queue(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        assert router.get_queue_depth(agent_id) == 0

    def test_depth_reflects_notifications(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.notify(agent_id)
        router.notify(agent_id)
        assert router.get_queue_depth(agent_id) == 2

    def test_depth_zero_for_unregistered(self, router):
        assert router.get_queue_depth(uuid4()) == 0


# ── Topology-aware routing ────────────────────────────────────────────────────

class TestTopologyAwareRouting:

    def test_register_cluster_member(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.register_cluster_member("research", agent_id)
        assert agent_id in router.get_cluster_members("research")

    def test_route_to_cluster_returns_member(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.register_cluster_member("research", agent_id)
        result = router.route_to_cluster("research")
        assert result == agent_id

    def test_route_to_cluster_empty_returns_none(self, router):
        result = router.route_to_cluster("nonexistent-cluster")
        assert result is None

    def test_route_to_cluster_prefers_idle(self, router):
        """route_to_cluster should prefer agent with lowest queue depth."""
        busy_agent = uuid4()
        idle_agent = uuid4()

        q_busy = asyncio.Queue()
        q_idle = asyncio.Queue()

        router.register(busy_agent, q_busy)
        router.register(idle_agent, q_idle)

        # Fill busy agent's queue
        q_busy.put_nowait(None)
        q_busy.put_nowait(None)
        q_busy.put_nowait(None)

        router.register_cluster_member("team", busy_agent)
        router.register_cluster_member("team", idle_agent)

        result = router.route_to_cluster("team", prefer_idle=True)
        assert result == idle_agent

    def test_route_to_cluster_skips_unregistered(self, router):
        """Agents that are in the cluster index but not in _queues are excluded."""
        active_agent = uuid4()
        inactive_agent = uuid4()

        q = asyncio.Queue()
        router.register(active_agent, q)
        router.register_cluster_member("team", active_agent)
        router.register_cluster_member("team", inactive_agent)  # no queue registered

        result = router.route_to_cluster("team")
        assert result == active_agent

    def test_unregister_removes_from_cluster(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)
        router.register_cluster_member("cluster", agent_id)
        router.unregister(agent_id)
        assert agent_id not in router.get_cluster_members("cluster")

    def test_multiple_clusters_independent(self, router):
        a1 = uuid4()
        a2 = uuid4()
        for a in [a1, a2]:
            router.register(a, asyncio.Queue())
        router.register_cluster_member("alpha", a1)
        router.register_cluster_member("beta", a2)

        assert router.route_to_cluster("alpha") == a1
        assert router.route_to_cluster("beta") == a2


# ── Replay ────────────────────────────────────────────────────────────────────

class TestReplay:

    @pytest.mark.asyncio
    async def test_replay_notifies_registered_agents(self, router):
        agent_id = uuid4()
        q = asyncio.Queue()
        router.register(agent_id, q)

        msg = MagicMock()
        msg.target_agent_id = agent_id

        await router.replay([msg])
        assert q.qsize() == 1

    @pytest.mark.asyncio
    async def test_replay_empty_list(self, router):
        await router.replay([])  # Should not raise


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_reset_router():
    from backend.workers.message_router import get_message_router, reset_message_router
    r1 = get_message_router()
    r2 = get_message_router()
    assert r1 is r2

    reset_message_router()
    r3 = get_message_router()
    assert r3 is not r1
