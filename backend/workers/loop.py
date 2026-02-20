"""Universal per-agent loop with tool execution."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, Repository, Task
from backend.db.repositories.messages import AgentMessageRepository
from backend.llm.model_resolver import resolve_model
from backend.prompts.assembly import PromptAssembly
from backend.services.agent_service import AgentService
from backend.services.llm_service import LLMService
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService
from backend.tools.loop_registry import (
    RunContext,
    get_handlers_for_role,
    truncate_tool_output,
)
from backend.workers.message_router import get_message_router
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

MAX_ITERATIONS = 1000
MAX_LOOPBACKS = 3


async def _send_fallback_message(
    message_service: MessageService,
    agent: Agent,
    project: Repository,
    content: str,
    emit_agent_message: object,
) -> None:
    """Write a fallback channel message to the user and emit it via WebSocket.

    Called when the loop ends abnormally (LLM error, max_loopbacks, max_iterations)
    so the user is never left staring at a blank chat.
    """
    try:
        msg = await message_service.send(
            from_agent_id=agent.id,
            target_agent_id=USER_AGENT_ID,
            project_id=project.id,
            content=content,
            message_type="system",
        )
        if emit_agent_message:
            emit_agent_message(msg)
    except Exception as exc:
        logger.warning("Failed to send fallback message for agent %s: %s", agent.id, exc)


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
    handlers = get_handlers_for_role(agent.role)

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

    new_messages_text = PromptAssembly.format_incoming_messages(
        unread, agent_by_id, USER_AGENT_ID, assignment_context,
    )

    history = await agent_msg_repo.list_last_n_sessions(
        agent.id, session_id, n_sessions=5
    )
    memory_content = agent.memory
    if isinstance(memory_content, dict):
        memory_content = str(memory_content) if memory_content else None

    pa = PromptAssembly(agent, project, memory_content)
    pa.load_history(
        history,
        new_messages_text,
        known_tool_names=set(handlers.keys()),
    )

    if new_messages_text:
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

    logger.info(
        "Agent %s (%s) session %s started: unread=%d",
        agent.id,
        agent.role,
        session_id,
        len(unread),
    )
    resolved_model = resolve_model(
        agent.role,
        seniority=getattr(agent, "tier", None),
        model_override=agent.model,
    )

    summarization_injected = False

    while iteration < MAX_ITERATIONS:
        if interrupt_flag():
            await session_service.end_session_force(session_id, "interrupted")
            return "interrupted"

        # Inject summarization block when context pressure hits 70%
        if not summarization_injected and pa.context_pressure_ratio() >= 0.70:
            logger.info(
                "Agent %s context pressure %.0f%% — injecting summarization block",
                agent.id,
                pa.context_pressure_ratio() * 100,
            )
            pa.append_summarization()
            summarization_injected = True

        try:
            content, tool_calls = await llm.chat_completion_with_tools(
                model=resolved_model,
                system_prompt=pa.system_prompt,
                messages=pa.messages,
                tools=pa.tools,
            )
        except Exception as exc:
            logger.exception("LLM call failed for agent %s: %s", agent.id, exc)
            await session_service.end_session_error(session_id)
            await _send_fallback_message(
                message_service,
                agent,
                project,
                f"I encountered an error processing your request and could not respond. "
                f"Error: {type(exc).__name__}: {str(exc)[:200]}",
                emit_agent_message,
            )
            return "error"

        iteration += 1
        await session_service.increment_iteration(session_id)

        assistant_tool_input = {"__tool_calls__": tool_calls} if tool_calls else None
        await agent_msg_repo.create_message(
            agent_id=agent.id,
            project_id=project.id,
            role="assistant",
            content=content or "",
            loop_iteration=iteration,
            session_id=session_id,
            tool_input=assistant_tool_input,
        )
        if content and emit_text:
            emit_text(content)
        pa.append_assistant(content or "", tool_calls)

        if not tool_calls:
            loopbacks += 1
            if loopbacks >= MAX_LOOPBACKS:
                logger.warning(
                    "Agent %s hit max_loopbacks (%d) in session %s",
                    agent.id,
                    MAX_LOOPBACKS,
                    session_id,
                )
                await session_service.end_session_force(session_id, "max_loopbacks")
                await _send_fallback_message(
                    message_service,
                    agent,
                    project,
                    "I was unable to produce a valid response after several attempts. "
                    "Please try rephrasing your request.",
                    emit_agent_message,
                )
                return "max_loopbacks"
            pa.append_loopback()
            continue

        loopbacks = 0
        end_calls = [tc for tc in tool_calls if tc.get("name") == "end"]
        non_end_calls = [tc for tc in tool_calls if tc.get("name") != "end"]
        if end_calls and non_end_calls:
            for ec in end_calls:
                end_use_id = ec.get("id") or "end-solo-rule"
                pa.append_end_solo_warning(end_use_id)
                await agent_msg_repo.create_message(
                    agent_id=agent.id,
                    project_id=project.id,
                    role="tool",
                    content=pa.messages[-1]["content"],
                    loop_iteration=iteration,
                    session_id=session_id,
                    tool_name="end",
                    tool_input={"__tool_use_id__": end_use_id},
                    tool_output=pa.messages[-1]["content"],
                )

        for tc in non_end_calls:
            name = tc.get("name", "")
            tool_input = tc.get("input") or {}
            if emit_tool_call:
                emit_tool_call(name, tool_input)

            tool_use_id = tc.get("id", "")
            try:
                handler = handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"Unknown tool '{name}'")
                result_text = await handler(ctx, tool_input)
            except Exception as exc:
                result_text = truncate_tool_output(f"Tool '{name}' failed: {exc}")
                pa.append_tool_error(name, exc, tool_use_id)
                if emit_tool_result:
                    emit_tool_result(name, result_text)
                tool_input_stored = {"__tool_use_id__": tool_use_id, **tool_input}
                await agent_msg_repo.create_message(
                    agent_id=agent.id,
                    project_id=project.id,
                    role="tool",
                    content=result_text,
                    loop_iteration=iteration,
                    session_id=session_id,
                    tool_name=name,
                    tool_input=tool_input_stored,
                    tool_output=result_text,
                )
                continue

            result_text = truncate_tool_output(result_text)
            if emit_tool_result:
                emit_tool_result(name, result_text)
            pa.append_tool_result(name, result_text, tool_use_id)
            # After a successful update_memory, allow summarization to re-trigger
            # if context pressure remains high after the agent writes its summary.
            if name == "update_memory" and summarization_injected:
                summarization_injected = False
            tool_input_stored = {"__tool_use_id__": tool_use_id, **tool_input}
            await agent_msg_repo.create_message(
                agent_id=agent.id,
                project_id=project.id,
                role="tool",
                content=result_text,
                loop_iteration=iteration,
                session_id=session_id,
                tool_name=name,
                tool_input=tool_input_stored,
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

    logger.warning(
        "Agent %s hit max_iterations (%d) in session %s",
        agent.id,
        MAX_ITERATIONS,
        session_id,
    )
    await session_service.end_session_force(session_id, "max_iterations")
    await _send_fallback_message(
        message_service,
        agent,
        project,
        "My session exceeded the maximum number of iterations and was ended automatically. "
        "Please send a new message to continue.",
        emit_agent_message,
    )
    return "max_iterations"
