"""
Per-agent task: outer loop waits on notification queue, then runs inner loop.

One AgentWorker per agent. Registers its queue with MessageRouter.
On wake: load agent/project, create session, run_inner_loop, end session, set status sleeping.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, Repository
from backend.db.session import AsyncSessionLocal
from backend.workers.loop import run_inner_loop
from backend.workers.message_router import get_message_router
from backend.services.session_service import SessionService
from backend.websocket.manager import ws_manager

logger = logging.getLogger(__name__)


class AgentWorker:
    """One worker per agent. Outer loop: await queue.get() -> run inner loop."""

    def __init__(self, agent_id: UUID, project_id: UUID):
        self.agent_id = agent_id
        self.project_id = project_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._interrupt = False
        self._task: asyncio.Task | None = None

    def interrupt(self) -> None:
        """Signal the worker to break the inner loop at next iteration."""
        self._interrupt = True

    def _interrupt_flag(self) -> bool:
        return self._interrupt

    async def run(self) -> None:
        """Run the outer loop. Registers queue with MessageRouter."""
        router = get_message_router()
        router.register(self.agent_id, self._queue)

        try:
            while True:
                try:
                    await self._queue.get()
                except asyncio.CancelledError:
                    break
                self._interrupt = False
                async with AsyncSessionLocal() as db:
                    agent = None
                    sess = None
                    session_service = SessionService(db)
                    try:
                        result = await db.execute(
                            select(Agent).where(Agent.id == self.agent_id)
                        )
                        agent = result.scalar_one_or_none()
                        if not agent:
                            logger.warning("Agent %s not found, skip wake", self.agent_id)
                            continue
                        proj_result = await db.execute(
                            select(Repository).where(Repository.id == agent.project_id)
                        )
                        project = proj_result.scalar_one_or_none()
                        if not project:
                            logger.warning("Project %s not found for agent %s", agent.project_id, self.agent_id)
                            continue

                        sess = await session_service.create_session(
                            agent.id,
                            project.id,
                            trigger_message_id=None,
                        )
                        agent.status = "active"
                        await db.flush()

                        end_reason = await run_inner_loop(
                            agent,
                            project,
                            sess.id,
                            trigger_message_id=None,
                            db=db,
                            interrupt_flag=self._interrupt_flag,
                            emit_text=lambda content: asyncio.create_task(
                                ws_manager.broadcast_agent_text(
                                    project.id,
                                    agent.id,
                                    agent.role,
                                    content,
                                    session_id=sess.id,
                                    iteration=sess.iteration_count or 0,
                                )
                            ),
                            emit_tool_call=lambda name, tool_input: asyncio.create_task(
                                ws_manager.broadcast_agent_tool_call(
                                    project.id,
                                    agent.id,
                                    agent.role,
                                    name,
                                    tool_input,
                                    session_id=sess.id,
                                    iteration=sess.iteration_count or 0,
                                )
                            ),
                            emit_tool_result=lambda name, output: asyncio.create_task(
                                ws_manager.broadcast_agent_tool_result(
                                    project.id,
                                    agent.id,
                                    name,
                                    output,
                                    success=not output.startswith("Tool"),
                                    session_id=sess.id,
                                    iteration=sess.iteration_count or 0,
                                    agent_role=agent.role,
                                )
                            ),
                            emit_agent_message=lambda msg: asyncio.create_task(
                                ws_manager.broadcast_agent_message(
                                    project.id,
                                    msg.id,
                                    msg.from_agent_id or agent.id,
                                    msg.target_agent_id or USER_AGENT_ID,
                                    msg.content,
                                    message_type=msg.message_type,
                                    created_at=msg.created_at,
                                )
                            ),
                        )
                        logger.info(
                            "Agent %s session ended: %s",
                            self.agent_id,
                            end_reason,
                        )
                    except Exception as e:
                        logger.exception("Agent worker %s error: %s", self.agent_id, e)
                        await db.rollback()
                        try:
                            if sess is not None:
                                await session_service.end_session_error(sess.id)
                            if agent is None:
                                retry_result = await db.execute(
                                    select(Agent).where(Agent.id == self.agent_id)
                                )
                                agent = retry_result.scalar_one_or_none()
                            if agent is not None:
                                agent.status = "sleeping"
                                await db.commit()
                        except Exception:
                            await db.rollback()
                        logger.warning(
                            "Agent worker %s recovered from cycle failure; awaiting next wake signal",
                            self.agent_id,
                        )
                        continue
                    else:
                        agent.status = "sleeping"
                        await db.commit()
        finally:
            router.unregister(self.agent_id)
            logger.debug("Agent worker %s stopped", self.agent_id)


def create_agent_worker(agent_id: UUID, project_id: UUID) -> AgentWorker:
    return AgentWorker(agent_id, project_id)
