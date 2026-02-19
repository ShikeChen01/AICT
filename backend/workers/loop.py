"""Universal per-agent loop with tool execution."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, Repository, Task
from backend.db.repositories.messages import AgentMessageRepository
from backend.services.agent_service import AgentService
from backend.services.llm_service import LLMService
from backend.services.message_service import MessageService
from backend.services.prompt_service import build_system_prompt, get_loopback_block
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService
from backend.tools.loop_registry import (
    RunContext,
    get_handlers_for_role,
    get_tool_defs_for_role,
    truncate_tool_output,
)
from backend.workers.message_router import get_message_router

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 1000
MAX_LOOPBACKS = 3


async def _assignment_message_for_agent(db: AsyncSession, agent: Agent) -> str | None:
    """Build assignment context when no unread channel message exists."""
    if not agent.current_task_id:
        return None

    result = await db.execute(select(Task).where(Task.id == agent.current_task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return None
    if task.assigned_agent_id != agent.id:
        return None
    if task.status in {"done", "aborted"}:
        return None

    lines = [
        f"Task assigned: {task.title}",
        f"Task ID: {task.id}",
        f"Status: {task.status}",
    ]
    if task.module_path:
        lines.append(f"Module: {task.module_path}")
    if task.description:
        lines.extend(["", task.description])
    return "\n".join(lines)


async def run_inner_loop(
    agent: Agent,
    project: Repository,
    session_id: UUID,
    trigger_message_id: UUID | None,
    *,
    db: AsyncSession,
    interrupt_flag: callable[[], bool],
    emit_text: callable[[str], None] | None = None,
    emit_tool_call: callable[[str, dict], None] | None = None,
    emit_tool_result: callable[[str, str], None] | None = None,
    emit_agent_message: callable[[object], None] | None = None,
) -> str:
    """Run wake-to-END loop for one agent session."""
    message_service = MessageService(db)
    session_service = SessionService(db)
    task_service = TaskService(db)
    agent_service = AgentService(db)
    agent_msg_repo = AgentMessageRepository(db)
    llm = LLMService()

    unread = await message_service.get_unread_for_agent(agent.id)
    assignment_context = None
    if not unread:
        assignment_context = await _assignment_message_for_agent(db, agent)
        if not assignment_context:
            await session_service.end_session(session_id, end_reason="normal_end", status="completed")
            return "normal_end"
    else:
        await message_service.mark_received([m.id for m in unread])

    result = await db.execute(select(Agent).where(Agent.project_id == project.id))
    project_agents = list(result.scalars().all())
    agent_by_id = {a.id: a for a in project_agents}

    def sender_name(aid: UUID | None) -> str:
        if aid is None:
            return "System"
        if aid == USER_AGENT_ID:
            return "User"
        a = agent_by_id.get(aid)
        return a.display_name if a else str(aid)

    message_chunks = [
        (
            f"[Message from {sender_name(m.from_agent_id)} "
            f"({agent_by_id.get(m.from_agent_id).role if m.from_agent_id in agent_by_id else 'user'}, "
            f"id={m.from_agent_id})]: {m.content}"
        )
        if m.from_agent_id != USER_AGENT_ID
        else f"[Message from User (id={USER_AGENT_ID})]: {m.content}"
        for m in unread
    ]
    if assignment_context:
        message_chunks.append(f"[Message from System (system)]: {assignment_context}")
    new_messages_text = "\n".join(message_chunks).strip()

    history = await agent_msg_repo.list_by_session(session_id, limit=500)
    memory_content = agent.memory
    if isinstance(memory_content, dict):
        memory_content = str(memory_content) if memory_content else None
    system_prompt = build_system_prompt(agent, project, memory_content)

    messages: list[dict] = []
    for h in history:
        if h.role in ("user", "assistant"):
            messages.append({"role": h.role, "content": h.content or ""})
        elif h.role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "content": h.content or "",
                    "tool_use_id": h.tool_name or "",
                }
            )
    if new_messages_text:
        messages.append({"role": "user", "content": new_messages_text})
        await agent_msg_repo.create_message(
            agent_id=agent.id,
            project_id=project.id,
            role="user",
            content=new_messages_text,
            loop_iteration=0,
            session_id=session_id,
        )

    iteration = 0
    loopbacks = 0
    tool_defs = get_tool_defs_for_role(agent.role)
    handlers = get_handlers_for_role(agent.role)

    ctx = RunContext(
        db=db,
        agent=agent,
        project=project,
        session_id=session_id,
        message_service=message_service,
        session_service=session_service,
        task_service=task_service,
        agent_service=agent_service,
        agent_msg_repo=agent_msg_repo,
        emit_agent_message=emit_agent_message,
    )

    while iteration < MAX_ITERATIONS:
        if interrupt_flag():
            await session_service.end_session_force(session_id, "interrupted")
            return "interrupted"

        try:
            content, tool_calls = await llm.chat_completion_with_tools(
                model=agent.model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tool_defs,
            )
        except Exception as exc:
            logger.exception("LLM call failed for agent %s: %s", agent.id, exc)
            await session_service.end_session_error(session_id)
            return "error"

        iteration += 1
        await session_service.increment_iteration(session_id)

        await agent_msg_repo.create_message(
            agent_id=agent.id,
            project_id=project.id,
            role="assistant",
            content=content or "",
            loop_iteration=iteration,
            session_id=session_id,
        )
        if content:
            if emit_text:
                emit_text(content)
            messages.append({"role": "assistant", "content": content})

        if not tool_calls:
            loopbacks += 1
            if loopbacks >= MAX_LOOPBACKS:
                await session_service.end_session_force(session_id, "max_loopbacks")
                return "max_loopbacks"
            messages.append({"role": "user", "content": get_loopback_block()})
            continue

        loopbacks = 0
        end_calls = [tc for tc in tool_calls if tc.get("name") == "end"]
        non_end_calls = [tc for tc in tool_calls if tc.get("name") != "end"]
        if end_calls and non_end_calls:
            note = "END was called with other tools and was ignored for this iteration. Call END alone."
            messages.append({"role": "tool", "content": note, "tool_use_id": "end-solo-rule"})
            await agent_msg_repo.create_message(
                agent_id=agent.id,
                project_id=project.id,
                role="tool",
                content=note,
                loop_iteration=iteration,
                session_id=session_id,
                tool_name="end",
                tool_input={},
                tool_output=note,
            )

        for tc in non_end_calls:
            name = tc.get("name", "")
            tool_input = tc.get("input") or {}
            if emit_tool_call:
                emit_tool_call(name, tool_input)

            try:
                handler = handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"Unknown tool '{name}'")
                result_text = await handler(ctx, tool_input)
            except Exception as exc:
                result_text = f"Tool '{name}' failed: {exc}"

            result_text = truncate_tool_output(result_text)
            if emit_tool_result:
                emit_tool_result(name, result_text)
            messages.append({"role": "tool", "content": result_text, "tool_use_id": tc.get("id", "")})
            await agent_msg_repo.create_message(
                agent_id=agent.id,
                project_id=project.id,
                role="tool",
                content=result_text,
                loop_iteration=iteration,
                session_id=session_id,
                tool_name=name,
                tool_input=tool_input,
                tool_output=result_text,
            )

        if end_calls and not non_end_calls:
            end_text = "Session ended."
            if emit_tool_result:
                emit_tool_result("end", end_text)
            await agent_msg_repo.create_message(
                agent_id=agent.id,
                project_id=project.id,
                role="tool",
                content=end_text,
                loop_iteration=iteration,
                session_id=session_id,
                tool_name="end",
                tool_input={},
                tool_output=end_text,
            )
            await session_service.end_session(session_id, end_reason="normal_end", status="completed")
            return "normal_end"

    await session_service.end_session_force(session_id, "max_iterations")
    return "max_iterations"
