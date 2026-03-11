"""
MessageRouter: singleton that receives send notifications, pushes wake-up to per-agent queues.

v3 enhancements:
  - Dead-letter queue: messages that cannot be delivered after MAX_NOTIFY_ATTEMPTS
    are moved to a dead_letter_messages table (if available) instead of silently dropped.
  - Topology-aware routing: route_to_cluster() sends a message to the agent in a named
    cluster with the least-loaded status (sleeping > active by queue depth).
  - Queue depth introspection: get_queue_depth() for scheduler / load-balancing decisions.

Original behavior preserved: notify() is still a fire-and-forget non-blocking put_nowait().
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from backend.db.models import ChannelMessage
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_router: "MessageRouter | None" = None

MAX_NOTIFY_ATTEMPTS: int = 3
_DEAD_LETTER_ENABLED: bool = True  # set False to disable DLQ (e.g. in tests)


class MessageRouter:
    """
    Singleton. Holds agent_id -> asyncio.Queue for wake-up signals (no payload).

    v3 additions:
    - _notify_counts: tracks consecutive failed notifies per agent (DLQ gate)
    - _cluster_index: cluster_name -> list[agent_id] for topology-aware routing
    """

    def __init__(self) -> None:
        self._queues: dict[UUID, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._notify_counts: dict[UUID, int] = {}    # consecutive failure count per agent
        self._cluster_index: dict[str, list[UUID]] = {}  # cluster_name -> agent_ids

    def register(self, agent_id: UUID, queue: asyncio.Queue) -> None:
        """Register an agent's notification queue (called by AgentWorker on startup)."""
        self._queues[agent_id] = queue
        self._notify_counts.pop(agent_id, None)  # reset failure count on re-register
        logger.debug("MessageRouter registered agent %s", agent_id)

    def unregister(self, agent_id: UUID) -> None:
        """Remove an agent's queue."""
        self._queues.pop(agent_id, None)
        self._notify_counts.pop(agent_id, None)
        # Remove from cluster index
        for members in self._cluster_index.values():
            if agent_id in members:
                members.remove(agent_id)

    def register_cluster_member(self, cluster_name: str, agent_id: UUID) -> None:
        """
        Register an agent as a member of a named cluster.

        Called by WorkerManager when spawning agents that have a cluster_name in their
        memory blob. Enables topology-aware routing via route_to_cluster().
        """
        members = self._cluster_index.setdefault(cluster_name, [])
        if agent_id not in members:
            members.append(agent_id)
        logger.debug("MessageRouter: agent %s joined cluster '%s'", agent_id, cluster_name)

    def unregister_cluster_member(self, cluster_name: str, agent_id: UUID) -> None:
        """Remove an agent from a named cluster."""
        members = self._cluster_index.get(cluster_name, [])
        if agent_id in members:
            members.remove(agent_id)

    def get_queue_depth(self, agent_id: UUID) -> int:
        """Return the number of pending notifications in an agent's queue. 0 if not registered."""
        q = self._queues.get(agent_id)
        return q.qsize() if q is not None else 0

    def notify(self, agent_id: UUID) -> None:
        """
        Push a wake-up signal to the agent's queue (no payload). Non-blocking put_nowait.

        On repeated failures (MAX_NOTIFY_ATTEMPTS), escalates to DLQ instead of silently
        dropping (v3 enhancement).
        """
        q = self._queues.get(agent_id)
        if q is None:
            self._notify_counts[agent_id] = self._notify_counts.get(agent_id, 0) + 1
            fails = self._notify_counts[agent_id]
            if fails >= MAX_NOTIFY_ATTEMPTS and _DEAD_LETTER_ENABLED:
                logger.warning(
                    "MessageRouter: agent %s has no queue after %d attempts — "
                    "scheduling DLQ escalation",
                    agent_id, fails,
                )
                asyncio.create_task(_escalate_to_dead_letter(agent_id, "no_queue_registered"))
            else:
                logger.warning(
                    "MessageRouter: no queue for agent %s (attempt %d/%d)",
                    agent_id, fails, MAX_NOTIFY_ATTEMPTS,
                )
            return

        try:
            q.put_nowait(None)
            self._notify_counts.pop(agent_id, None)  # reset on success
            logger.debug("MessageRouter: notified agent %s", agent_id)
        except asyncio.QueueFull:
            logger.warning("MessageRouter: queue full for agent %s", agent_id)

    def route_to_cluster(self, cluster_name: str, prefer_idle: bool = True) -> UUID | None:
        """
        Topology-aware routing: return the best agent_id in a named cluster to receive
        the next message, or None if the cluster has no registered members.

        Selection policy (prefer_idle=True):
        - Prefer agents whose queue depth is 0 (idle — least loaded).
        - Among tied agents, pick the first registered (stable order).

        This enables a basic work-stealing scheduler without a full orchestrator.
        """
        members = self._cluster_index.get(cluster_name, [])
        active_members = [m for m in members if m in self._queues]
        if not active_members:
            return None

        if prefer_idle:
            # Sort by queue depth ascending — pick least loaded
            active_members.sort(key=lambda aid: self.get_queue_depth(aid))

        target = active_members[0]
        logger.debug(
            "MessageRouter: routed to cluster '%s' -> agent %s (queue_depth=%d)",
            cluster_name, target, self.get_queue_depth(target),
        )
        return target

    def get_cluster_members(self, cluster_name: str) -> list[UUID]:
        """Return the list of registered agent IDs for a cluster."""
        return list(self._cluster_index.get(cluster_name, []))

    async def replay(self, messages: list[ChannelMessage]) -> None:
        """On startup: for each undelivered message, notify the target agent."""
        async with self._lock:
            for msg in messages:
                if msg.target_agent_id is not None:
                    self.notify(msg.target_agent_id)
        if messages:
            logger.info("MessageRouter replayed %d undelivered messages", len(messages))


# ── Dead-letter escalation ────────────────────────────────────────────────────


async def _escalate_to_dead_letter(agent_id: UUID, reason: str) -> None:
    """
    Write an entry to the dead_letter_messages table for an undeliverable notification.

    This is a best-effort async task — failures are logged but not re-raised.
    """
    try:
        from backend.db.session import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            # Check table exists (graceful pre-migration behavior)
            check = await db.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'dead_letter_messages'")
            )
            if check.scalar_one() == 0:
                return

            await db.execute(
                text(
                    "INSERT INTO dead_letter_messages "
                    "(id, target_agent_id, reason, retry_count, created_at, last_attempted_at) "
                    "VALUES (gen_random_uuid(), :agent_id, :reason, 0, :now, :now)"
                ),
                {
                    "agent_id": str(agent_id),
                    "reason": reason,
                    "now": datetime.now(tz=timezone.utc),
                },
            )
            await db.commit()
            logger.info("MessageRouter: DLQ entry created for agent %s (reason=%s)", agent_id, reason)
    except Exception as exc:
        logger.warning("MessageRouter: DLQ escalation failed for agent %s: %s", agent_id, exc)


# ── Singleton ─────────────────────────────────────────────────────────────────


def get_message_router() -> MessageRouter:
    """Return the singleton MessageRouter. Creates it on first access."""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router


def reset_message_router() -> None:
    """Reset singleton (for tests / startup retry)."""
    global _router
    _router = None
