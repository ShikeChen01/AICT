"""
MessageRouter: singleton that receives send notifications, pushes wake-up to per-agent queues.

Does not write to DB (message_service writes). On startup, replay undelivered
messages by notifying each target agent's queue. Agent workers (Agent 2) register
their queue via register(agent_id, queue).
"""

import asyncio
from uuid import UUID

from backend.db.models import ChannelMessage
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_router: "MessageRouter | None" = None


class MessageRouter:
    """Singleton. Holds agent_id -> asyncio.Queue for wake-up signals (no payload)."""

    def __init__(self) -> None:
        self._queues: dict[UUID, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    def register(self, agent_id: UUID, queue: asyncio.Queue) -> None:
        """Register an agent's notification queue (called by WorkerManager/AgentWorker)."""
        self._queues[agent_id] = queue
        logger.debug("MessageRouter registered agent %s", agent_id)

    def unregister(self, agent_id: UUID) -> None:
        """Remove an agent's queue."""
        self._queues.pop(agent_id, None)

    def notify(self, agent_id: UUID) -> None:
        """Push a wake-up signal to the agent's queue (no payload). Non-blocking put."""
        q = self._queues.get(agent_id)
        if q is None:
            logger.warning(
                "MessageRouter: no queue registered for agent %s — worker may not have started. "
                "Agent will not process this wake-up signal.",
                agent_id,
            )
            return
        try:
            q.put_nowait(None)  # Sentinel: wake up, no payload
            logger.debug("MessageRouter: notified agent %s", agent_id)
        except asyncio.QueueFull:
            logger.warning("MessageRouter: queue full for agent %s", agent_id)

    async def replay(self, messages: list[ChannelMessage]) -> None:
        """On startup: for each undelivered message, notify the target agent."""
        async with self._lock:
            for msg in messages:
                if msg.target_agent_id is not None:
                    self.notify(msg.target_agent_id)
        if messages:
            logger.info("MessageRouter replayed %d undelivered messages", len(messages))


def get_message_router() -> MessageRouter:
    """Return the singleton MessageRouter. Creates it on first access."""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router


def reset_message_router() -> None:
    """Reset singleton (for tests)."""
    global _router
    _router = None
