"""
Engineer graph lifecycle: start and resume engineer tasks via LangGraph.

Replaces the role of EngineerWorker for new dispatches. Each engineer run
uses a unique thread_id for checkpointing and interrupt/resume support.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Task
from backend.db.session import AsyncSessionLocal
from backend.graph.engineer_graph import create_engineer_graph
from backend.graph.events import emit_agent_log
from backend.services.e2b_service import E2BService
from backend.services.orchestrator import sandbox_should_persist
from backend.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Single compiled engineer graph with in-memory checkpointer (per process)
_engineer_graph_app = None
_engineer_checkpointer = None


def _get_engineer_graph_app():
    """Build and compile the engineer graph once (with MemorySaver)."""
    global _engineer_graph_app, _engineer_checkpointer
    if _engineer_graph_app is None:
        _engineer_checkpointer = MemorySaver()
        _engineer_graph_app = create_engineer_graph().compile(
            checkpointer=_engineer_checkpointer
        )
    return _engineer_graph_app


def _thread_id(agent_id: UUID, task_id: UUID) -> str:
    return f"engineer-{agent_id}-{task_id}"


async def _wake_agent(session: AsyncSession, agent: Agent) -> None:
    """Ensure agent has a sandbox."""
    if agent.status == "sleeping":
        agent.status = "active"
    if not agent.sandbox_id:
        e2b = E2BService()
        await e2b.create_sandbox(
            session=session,
            agent=agent,
            persistent=sandbox_should_persist(agent.role),
        )
    await session.commit()


def _build_initial_state(agent: Agent, task: Task) -> dict:
    """Build EngineerState for the first invoke."""
    current_task = {
        "id": str(task.id),
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
    }
    task_prompt = (
        f"You have been assigned task: {task.title}\n\n"
        f"Description: {task.description or 'No description provided'}\n\n"
        f"Your agent_id is: {agent.id}\n"
        f"Project ID: {agent.project_id}\n"
        f"Task ID: {task.id}\n\n"
        "Please implement this task. Start by creating a branch, "
        "make your changes, test them, then commit and create a PR."
    )
    return {
        "messages": [HumanMessage(content=task_prompt)],
        "project_id": str(agent.project_id),
        "agent_id": str(agent.id),
        "task_id": str(task.id),
        "current_task": current_task,
        "pending_ticket_id": "",
        "abort_reason": "",
    }


async def _run_engineer_graph(
    agent_id: UUID,
    task_id: UUID,
    project_id: UUID,
    run_id: UUID,
) -> None:
    """
    Background task: run the engineer graph to completion (or until interrupt).
    Broadcasts job_* events and updates agent/task on completion/failure.
    """
    logger.info(
        "_run_engineer_graph entered (background): run_id=%s agent_id=%s task_id=%s project_id=%s",
        run_id,
        agent_id,
        task_id,
        project_id,
    )
    async with AsyncSessionLocal() as session:
        agent_result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        task_result = await session.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one_or_none()
        if not agent or not task:
            logger.error("Agent or task not found for graph run agent_id=%s task_id=%s", agent_id, task_id)
            await ws_manager.broadcast_job_failed(
                job_id=run_id,
                project_id=project_id,
                task_id=task_id,
                agent_id=agent_id,
                error="Agent or task not found",
            )
            return

    logger.info(
        "Engineer graph loaded agent and task: agent_id=%s task_id=%s task_title=%s",
        agent_id,
        task_id,
        task.title,
    )
    try:
        await ws_manager.broadcast_job_started(
            job_id=run_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            message=f"Starting: {task.title}",
        )
        await emit_agent_log(
            project_id=project_id,
            agent_id=agent_id,
            agent_role="engineer",
            log_type="thought",
            content=f"Starting task implementation: {task.title}",
        )

        async with AsyncSessionLocal() as session:
            await _wake_agent(session, agent)
            await session.refresh(agent)
            await session.refresh(task)

        app = _get_engineer_graph_app()
        config = {"configurable": {"thread_id": _thread_id(agent_id, task_id)}}
        initial_state = _build_initial_state(agent, task)

        logger.info(
            "Invoking engineer graph: run_id=%s thread_id=%s",
            run_id,
            _thread_id(agent_id, task_id),
        )
        # Invoke until completion or interrupt (stream or loop not required for first run)
        result = await app.ainvoke(initial_state, config=config)
        logger.info(
            "Engineer graph ainvoke returned: run_id=%s pending_ticket_id=%s",
            run_id,
            result.get("pending_ticket_id") or "",
        )

        # Check for interrupt (pending_ticket_id set) - if so, we paused and will resume later
        pending = result.get("pending_ticket_id") or ""
        if pending:
            logger.info("Engineer graph paused for ticket %s", pending)
            return

        # Completed: extract final message and update DB
        messages = result.get("messages", [])
        final_text = ""
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and not getattr(m, "tool_calls", None):
                final_text = (m.content if isinstance(m.content, str) else str(m.content))[:10000]
                break

        pr_url = None
        async with AsyncSessionLocal() as session:
            task_result = await session.execute(select(Task).where(Task.id == task_id))
            t = task_result.scalar_one_or_none()
            agent_result = await session.execute(select(Agent).where(Agent.id == agent_id))
            a = agent_result.scalar_one_or_none()
            if t:
                if t.pr_url:
                    t.status = "in_review"
                pr_url = t.pr_url
            if a:
                a.status = "active"
                a.current_task_id = None
            await session.commit()

        await ws_manager.broadcast_job_completed(
            job_id=run_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            result=final_text or "Task processed",
            pr_url=pr_url,
        )
        await emit_agent_log(
            project_id=project_id,
            agent_id=agent_id,
            agent_role="engineer",
            log_type="message",
            content=f"Job completed: {final_text[:500] if final_text else 'Task processed'}",
        )

        # Close ephemeral sandbox
        async with AsyncSessionLocal() as session:
            agent_result = await session.execute(select(Agent).where(Agent.id == agent_id))
            a = agent_result.scalar_one_or_none()
            if a and not sandbox_should_persist(a.role) and a.sandbox_id:
                try:
                    e2b = E2BService()
                    await e2b.close_sandbox(session, a)
                    await session.commit()
                except Exception as e:
                    logger.warning("Failed to close sandbox for %s: %s", agent_id, e)

    except Exception as exc:
        logger.exception("Engineer graph failed: %s", exc)
        async with AsyncSessionLocal() as session:
            a = (await session.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
            if a:
                a.status = "active"
                a.current_task_id = None
                await session.commit()
        await ws_manager.broadcast_job_failed(
            job_id=run_id,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            error=str(exc),
        )
        await emit_agent_log(
            project_id=project_id,
            agent_id=agent_id,
            agent_role="engineer",
            log_type="error",
            content=f"Job failed: {exc}",
        )


async def start_engineer_task(agent_id: UUID, task_id: UUID) -> str:
    """
    Start an engineer graph run in the background. Returns a run_id (used for job_* events).
    Caller must have already validated agent/task and set agent.status=busy, agent.current_task_id=task_id.
    """
    logger.info(
        "start_engineer_task called: agent_id=%s task_id=%s",
        agent_id,
        task_id,
    )
    async with AsyncSessionLocal() as session:
        project_result = await session.execute(
            select(Agent.project_id).where(Agent.id == agent_id)
        )
        project_id = project_result.scalar_one_or_none()
        if not project_id:
            logger.error(
                "Cannot start engineer task: agent_id=%s has no project_id",
                agent_id,
            )
            return ""
    run_id = uuid4()
    logger.info(
        "Scheduling _run_engineer_graph: run_id=%s agent_id=%s task_id=%s project_id=%s",
        run_id,
        agent_id,
        task_id,
        project_id,
    )

    def _log_task_done(t: asyncio.Task) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            logger.warning("Engineer graph task cancelled: run_id=%s agent_id=%s", run_id, agent_id)
        except Exception:  # noqa: BLE001
            logger.exception("Engineer graph background task failed: run_id=%s agent_id=%s task_id=%s", run_id, agent_id, task_id)

    task = asyncio.create_task(
        _run_engineer_graph(agent_id, task_id, project_id, run_id)
    )
    task.add_done_callback(_log_task_done)
    return str(run_id)


async def resume_engineer(
    agent_id: UUID,
    task_id: UUID,
    user_message: str,
) -> None:
    """
    Resume an interrupted engineer graph with the user's reply.
    The graph must have been paused via interrupt() (e.g. request_human_input tool).
    """
    app = _get_engineer_graph_app()
    config = {"configurable": {"thread_id": _thread_id(agent_id, task_id)}}
    # Resume: pass the user message as the return value of interrupt()
    cmd = Command(resume=user_message)
    await app.ainvoke(cmd, config=config)
    # After resume, the graph may complete or interrupt again; we don't wait for full completion
    # here - the background run continues from the tool that called interrupt().


def get_engineer_graph_service() -> "EngineerGraphService":
    """Return a simple service handle for dependency injection."""
    return EngineerGraphService()


class EngineerGraphService:
    """Thin wrapper for start_engineer_task and resume_engineer."""

    async def start_engineer_task(self, agent_id: UUID, task_id: UUID) -> str:
        return await start_engineer_task(agent_id, task_id)

    async def resume_engineer(
        self,
        agent_id: UUID,
        task_id: UUID,
        user_message: str,
    ) -> None:
        await resume_engineer(agent_id, task_id, user_message)
