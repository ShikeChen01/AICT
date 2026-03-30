"""
Per-agent task: outer loop waits on notification queue, then runs Agent.run().

One AgentWorker per agent. Registers its queue with MessageRouter.
On wake: load agent/project from DB, create session, run Agent.run(), end session,
set status sleeping.

The Agent instance is exposed via self.agent so ConfigListener can mark config
dirty for hot-reload mid-session.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.agent import Agent, EmitCallbacks
from backend.db.models import Agent as AgentRecord, Repository
from backend.db.session import AsyncSessionLocal
from backend.workers.message_router import get_message_router
from backend.services.session_service import SessionService
from backend.websocket.manager import ws_manager
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


class AgentWorker:
    """One worker per agent. Outer loop: await queue.get() -> Agent.run()."""

    def __init__(self, agent_id: UUID, project_id: UUID):
        self.agent_id = agent_id
        self.project_id = project_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._interrupt = False
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        # Exposed for ConfigListener — set while Agent.run() is active
        self.agent: Agent | None = None

    def interrupt(self) -> None:
        """Signal the worker to stop the inner loop immediately."""
        self._interrupt = True
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _interrupt_flag(self) -> bool:
        return self._interrupt

    async def wait_ready(self, timeout: float = 5.0) -> None:
        """Block until the worker has registered its queue with MessageRouter."""
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    def _build_callbacks(
        self,
        project: Repository,
        agent_record: AgentRecord,
        sess,
    ) -> EmitCallbacks:
        """Build WebSocket emission callbacks for an agent session."""
        return EmitCallbacks(
            emit_text=lambda content: asyncio.create_task(
                ws_manager.broadcast_agent_text(
                    project.id,
                    agent_record.id,
                    agent_record.role,
                    content,
                    session_id=sess.id,
                    iteration=sess.iteration_count or 0,
                )
            ),
            emit_tool_call=lambda name, tool_input: asyncio.create_task(
                ws_manager.broadcast_agent_tool_call(
                    project.id,
                    agent_record.id,
                    agent_record.role,
                    name,
                    tool_input,
                    session_id=sess.id,
                    iteration=sess.iteration_count or 0,
                )
            ),
            emit_tool_result=lambda name, output: asyncio.create_task(
                ws_manager.broadcast_agent_tool_result(
                    project.id,
                    agent_record.id,
                    name,
                    output,
                    success=not output.startswith("Tool"),
                    session_id=sess.id,
                    iteration=sess.iteration_count or 0,
                    agent_role=agent_record.role,
                )
            ),
            emit_agent_message=lambda msg: asyncio.create_task(
                ws_manager.broadcast_agent_message(
                    project.id,
                    msg.id,
                    msg.from_agent_id or agent_record.id,
                    msg.target_agent_id,
                    msg.content,
                    message_type=msg.message_type,
                    created_at=msg.created_at,
                    target_user_id=msg.target_user_id,
                )
            ),
        )

    async def run(self) -> None:
        """Run the outer loop. Registers queue with MessageRouter."""
        router = get_message_router()
        router.register(self.agent_id, self._queue)
        self._ready.set()

        try:
            while True:
                try:
                    await self._queue.get()
                except asyncio.CancelledError:
                    break
                self._interrupt = False
                async with AsyncSessionLocal() as db:
                    session_service = SessionService(db)
                    agent_record = None
                    sess = None
                    needs_rollback_before_reset = False

                    try:
                        result = await db.execute(
                            select(AgentRecord)
                            .options(selectinload(AgentRecord.sandbox), selectinload(AgentRecord.desktop))
                            .where(AgentRecord.id == self.agent_id)
                        )
                        agent_record = result.scalar_one_or_none()
                        if not agent_record:
                            logger.warning("Agent %s not found, skip wake", self.agent_id)
                            continue

                        proj_result = await db.execute(
                            select(Repository).where(Repository.id == agent_record.project_id)
                        )
                        project = proj_result.scalar_one_or_none()
                        if not project:
                            logger.warning(
                                "Project %s not found for agent %s",
                                agent_record.project_id,
                                self.agent_id,
                            )
                            continue

                        agent_record.status = "active"
                        await db.flush()
                        sess = await session_service.create_session(
                            agent_record.id,
                            project.id,
                            trigger_message_id=None,
                        )

                        callbacks = self._build_callbacks(project, agent_record, sess)
                        agent_instance = Agent(
                            record=agent_record,
                            project=project,
                            db=db,
                            callbacks=callbacks,
                            interrupt_flag=self._interrupt_flag,
                        )
                        # Expose for ConfigListener
                        self.agent = agent_instance

                        self._task = asyncio.create_task(
                            agent_instance.run(sess.id, trigger_message_id=None)
                        )
                        try:
                            end_reason = await self._task
                        except asyncio.CancelledError:
                            worker_shutdown = not self._interrupt
                            end_reason = "interrupted"
                            needs_rollback_before_reset = True
                            if self._task is not None and not self._task.done():
                                self._task.cancel()
                                try:
                                    await self._task
                                except asyncio.CancelledError:
                                    pass
                            try:
                                await session_service.end_session_force(sess.id, "interrupted")
                            except Exception:
                                pass
                            if worker_shutdown:
                                raise
                        except Exception as loop_exc:
                            logger.exception(
                                "Agent worker %s: unhandled exception from Agent.run: %s",
                                self.agent_id,
                                loop_exc,
                            )
                            try:
                                await session_service.end_session_error(sess.id)
                            except Exception:
                                pass
                            raise
                        finally:
                            self._task = None
                            self.agent = None

                        logger.info("Agent %s session ended: %s", self.agent_id, end_reason)

                    except Exception as cycle_exc:
                        logger.exception(
                            "Agent worker %s cycle error: %s",
                            self.agent_id,
                            cycle_exc,
                        )
                        await db.rollback()
                    finally:
                        try:
                            if needs_rollback_before_reset:
                                await db.rollback()
                            refresh_result = await db.execute(
                                select(AgentRecord).where(AgentRecord.id == self.agent_id)
                            )
                            live_agent = refresh_result.scalar_one_or_none()
                            if live_agent is not None:
                                live_agent.status = "sleeping"
                            await db.commit()
                        except Exception as commit_exc:
                            logger.error(
                                "Agent worker %s: failed to reset status to sleeping: %s",
                                self.agent_id,
                                commit_exc,
                            )
                            await db.rollback()

                    logger.debug(
                        "Agent worker %s cycle complete, awaiting next wake signal",
                        self.agent_id,
                    )
        finally:
            self.agent = None
            router.unregister(self.agent_id)
            logger.debug("Agent worker %s stopped", self.agent_id)


def create_agent_worker(agent_id: UUID, project_id: UUID) -> AgentWorker:
    return AgentWorker(agent_id, project_id)
