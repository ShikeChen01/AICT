"""
WorkerManager: startup and shutdown of MessageRouter and AgentWorkers.

On startup: run migrations (if configured), init MessageRouter, load agents from DB,
replay undelivered messages into queues, spawn one AgentWorker per agent.
On shutdown: cancel workers, unregister queues, stop router, close sandboxes, DB pool.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent
from backend.db.session import AsyncSessionLocal
from backend.workers.message_router import get_message_router, reset_message_router
from backend.workers.agent_worker import AgentWorker
from backend.services.message_service import MessageService

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages MessageRouter and per-agent AgentWorker tasks."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._workers: list[AgentWorker] = []

    async def start(self) -> None:
        """Start MessageRouter, replay undelivered, load agents, spawn workers."""
        router = get_message_router()

        async with AsyncSessionLocal() as session:
            msg_service = MessageService(session)
            undelivered = await msg_service.get_undelivered_for_replay()
            await session.commit()

        await router.replay(undelivered)

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Agent))
            agents = list(result.scalars().all())
            await session.commit()

        for agent in agents:
            worker = AgentWorker(agent.id, agent.project_id)
            self._workers.append(worker)
            task = asyncio.create_task(worker.run())
            self._tasks.append(task)
            logger.info("Spawned AgentWorker for agent %s (%s)", agent.id, agent.display_name)

        logger.info("WorkerManager started: %d agents", len(self._workers))

    async def stop(self) -> None:
        """Cancel all worker tasks, unregister queues, reset router."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()
        self._workers.clear()
        reset_message_router()
        logger.info("WorkerManager stopped")

    def interrupt_agent(self, agent_id: UUID) -> None:
        """Signal a specific agent's worker to interrupt at next iteration."""
        for w in self._workers:
            if w.agent_id == agent_id:
                w.interrupt()
                return
        logger.debug("No worker found for agent %s to interrupt", agent_id)


_worker_manager: WorkerManager | None = None


def get_worker_manager() -> WorkerManager:
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager()
    return _worker_manager
