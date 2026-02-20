"""
WorkerManager: startup and shutdown of MessageRouter and AgentWorkers.

On startup: run migrations (if configured), init MessageRouter, load agents from DB,
replay undelivered messages into queues, spawn one AgentWorker per agent.
On shutdown: cancel workers, unregister queues, stop router, close sandboxes, DB pool.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent
from backend.db.session import AsyncSessionLocal
from backend.workers.message_router import get_message_router, reset_message_router
from backend.workers.agent_worker import AgentWorker
from backend.services.message_service import MessageService
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


class WorkerManager:
    """Manages MessageRouter and per-agent AgentWorker tasks."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._workers: list[AgentWorker] = []
        self._task_meta: dict[asyncio.Task, tuple[UUID, UUID]] = {}
        self._shutting_down = False
        self._started = False
        self._removing: set[UUID] = set()

    def _track_worker(self, worker: AgentWorker, task: asyncio.Task) -> None:
        self._workers.append(worker)
        self._tasks.append(task)
        self._task_meta[task] = (worker.agent_id, worker.project_id)
        task.add_done_callback(self._on_worker_done)

    async def _spawn_tracked_worker(self, agent_id: UUID, project_id: UUID) -> None:
        worker = AgentWorker(agent_id, project_id)
        task = asyncio.create_task(worker.run())
        self._track_worker(worker, task)
        logger.info("Spawned AgentWorker for agent %s", agent_id)

    def _on_worker_done(self, task: asyncio.Task) -> None:
        metadata = self._task_meta.pop(task, None)
        if task in self._tasks:
            self._tasks.remove(task)
        if metadata is None:
            return

        agent_id, project_id = metadata
        self._workers = [worker for worker in self._workers if worker.agent_id != agent_id]

        if self._shutting_down or agent_id in self._removing:
            self._removing.discard(agent_id)
            return

        if task.cancelled():
            logger.warning("AgentWorker task for agent %s was cancelled unexpectedly; respawning", agent_id)
        else:
            exc = task.exception()
            if exc is None:
                logger.warning("AgentWorker task for agent %s exited unexpectedly; respawning", agent_id)
            else:
                logger.exception("AgentWorker task for agent %s crashed; respawning", agent_id, exc_info=exc)

        asyncio.create_task(self._spawn_tracked_worker(agent_id, project_id))

    @property
    def is_started(self) -> bool:
        """True after start() completes successfully."""
        return self._started

    @property
    def worker_count(self) -> int:
        """Number of currently tracked AgentWorker tasks."""
        return len(self._workers)

    def get_status(self) -> dict:
        """Return a serialisable status dict for diagnostics / health endpoints."""
        return {
            "started": self._started,
            "shutting_down": self._shutting_down,
            "worker_count": len(self._workers),
            "agent_ids": [str(w.agent_id) for w in self._workers],
        }

    async def start(self) -> None:
        """Start MessageRouter, replay undelivered, load agents, spawn workers."""
        self._shutting_down = False
        self._started = False
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
            await self._spawn_tracked_worker(agent.id, agent.project_id)
            logger.info("Worker ready for agent %s (%s)", agent.id, agent.display_name)

        self._started = True
        logger.info("WorkerManager started: %d agents", len(self._workers))

    async def stop(self) -> None:
        """Cancel all worker tasks, unregister queues, reset router."""
        self._shutting_down = True
        self._started = False
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()
        self._workers.clear()
        self._task_meta.clear()
        reset_message_router()
        logger.info("WorkerManager stopped")

    async def spawn_worker(self, agent_id: UUID, project_id: UUID) -> None:
        """Spawn a new worker at runtime and wait until its queue is registered."""
        if any(worker.agent_id == agent_id for worker in self._workers):
            logger.debug("Worker already exists for agent %s; skipping duplicate spawn", agent_id)
            return
        await self._spawn_tracked_worker(agent_id, project_id)
        worker = next((w for w in self._workers if w.agent_id == agent_id), None)
        if worker is not None:
            try:
                await worker.wait_ready()
            except asyncio.TimeoutError:
                logger.warning("Worker for agent %s did not become ready in time", agent_id)

    def interrupt_agent(self, agent_id: UUID) -> None:
        """Signal a specific agent's worker to interrupt at next iteration."""
        for w in self._workers:
            if w.agent_id == agent_id:
                w.interrupt()
                return
        logger.debug("No worker found for agent %s to interrupt", agent_id)

    async def remove_worker(self, agent_id: UUID) -> None:
        """Permanently stop a worker and prevent auto-respawn.

        Marks the agent as being removed, interrupts its current session,
        cancels the asyncio task, and deregisters its message queue.
        Safe to call even if no worker exists for the given agent.
        """
        self._removing.add(agent_id)

        worker = next((w for w in self._workers if w.agent_id == agent_id), None)
        task = next(
            (t for t, meta in self._task_meta.items() if meta[0] == agent_id), None
        )

        if worker is not None:
            worker.interrupt()

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        self._workers = [w for w in self._workers if w.agent_id != agent_id]
        self._tasks = [t for t in self._tasks if self._task_meta.get(t, (None,))[0] != agent_id]
        self._task_meta = {t: meta for t, meta in self._task_meta.items() if meta[0] != agent_id}
        self._removing.discard(agent_id)

        get_message_router().unregister(agent_id)
        logger.info("Removed worker for agent %s", agent_id)


_worker_manager: WorkerManager | None = None


def get_worker_manager() -> WorkerManager:
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager()
    return _worker_manager


def reset_worker_manager() -> None:
    """Reset singleton (used during startup retry to get a clean instance)."""
    global _worker_manager
    _worker_manager = None
