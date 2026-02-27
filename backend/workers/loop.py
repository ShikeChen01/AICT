"""Universal per-agent loop with tool execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, Repository, Task
from backend.db.repositories.llm_usage import LLMUsageRepository
from backend.db.repositories.messages import AgentMessageRepository
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.llm.model_resolver import resolve_model
from backend.llm.pricing import estimate_cost_usd
from backend.prompts.assembly import PromptAssembly
from backend.websocket.manager import Channel, ws_manager
from backend.services.agent_service import AgentService
from backend.services.llm_service import LLMService
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService
from backend.tools.loop_registry import (
    RunContext,
    get_handlers_for_role,
    truncate_tool_output,
    validate_tool_input,
)
from backend.workers.message_router import get_message_router
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

MAX_ITERATIONS = 1000
MAX_LOOPBACKS = 3
# Check for new human messages every N iterations while the loop is running
MID_LOOP_MSG_CHECK_INTERVAL = 5
# Rate limit soft-pause: poll interval and maximum total wait before giving up
RATE_LIMIT_POLL_SECONDS = 5
RATE_LIMIT_MAX_WAIT_SECONDS = 600  # 10 minutes


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


async def _rate_limit_soft_pause(
    *,
    usage_repo: "LLMUsageRepository",
    ps_repo: "ProjectSettingsRepository",
    project_id: UUID,
    agent_id: UUID,
    interrupt_flag: callable[[], bool],
) -> tuple[str | None, dict]:
    """Soft-pause the loop until hourly rate limits clear or the user adjusts them.

    Polls DB every ``RATE_LIMIT_POLL_SECONDS``.  Each poll re-reads project settings
    so a user adjusting limits from the frontend takes effect within one cycle.

    Returns:
        (end_reason, fresh_limits) where end_reason is None if we can proceed,
        or "interrupted" / "rate_limited_timeout" if we must abort.
        fresh_limits is the latest limits dict (may have changed during the pause).
    """
    wait_total = 0
    notified = False
    while wait_total < RATE_LIMIT_MAX_WAIT_SECONDS:
        await asyncio.sleep(RATE_LIMIT_POLL_SECONDS)
        wait_total += RATE_LIMIT_POLL_SECONDS

        if interrupt_flag():
            return "interrupted", {}

        # Re-read settings — picks up any limit changes the user made via PATCH /settings
        fresh_ps = await ps_repo.get_by_project(project_id)
        calls_limit = (fresh_ps.calls_per_hour_limit or 0) if fresh_ps else 0
        tokens_limit = (fresh_ps.tokens_per_hour_limit or 0) if fresh_ps else 0

        # If user cleared all rate limits, resume immediately
        if calls_limit == 0 and tokens_limit == 0:
            logger.info("Agent %s: rate limits cleared by user — resuming", agent_id)
            return None, {
                "calls_per_hour_limit": 0,
                "tokens_per_hour_limit": 0,
                "daily_token_budget": (fresh_ps.daily_token_budget or 0) if fresh_ps else 0,
                "daily_cost_budget_usd": (fresh_ps.daily_cost_budget_usd or 0.0) if fresh_ps else 0.0,
            }

        hourly = await usage_repo.hourly_stats(project_id)
        calls_ok = calls_limit == 0 or hourly["calls"] < calls_limit
        tokens_ok = tokens_limit == 0 or hourly["tokens"] < tokens_limit
        if calls_ok and tokens_ok:
            if notified:
                logger.info("Agent %s: rate limit window cleared — resuming", agent_id)
            return None, {
                "calls_per_hour_limit": calls_limit,
                "tokens_per_hour_limit": tokens_limit,
                "daily_token_budget": (fresh_ps.daily_token_budget or 0) if fresh_ps else 0,
                "daily_cost_budget_usd": (fresh_ps.daily_cost_budget_usd or 0.0) if fresh_ps else 0.0,
            }

        if not notified:
            logger.info(
                "Agent %s: rate-limited (calls=%d/%d tokens=%d/%d) — soft-pausing (max %ds)",
                agent_id,
                hourly["calls"], calls_limit or 0,
                hourly["tokens"], tokens_limit or 0,
                RATE_LIMIT_MAX_WAIT_SECONDS,
            )
            notified = True

    # Exhausted max wait — end session
    return "rate_limited_timeout", {}


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

    # Phase 3 + 4: load project-level settings (model/prompt overrides + all limits)
    ps_repo = ProjectSettingsRepository(db)
    project_settings = await ps_repo.get_by_project(project.id)
    model_overrides = (project_settings.model_overrides or {}) if project_settings else {}
    prompt_overrides = (project_settings.prompt_overrides or {}) if project_settings else {}
    daily_token_budget = (project_settings.daily_token_budget or 0) if project_settings else 0
    calls_per_hour_limit = (project_settings.calls_per_hour_limit or 0) if project_settings else 0
    tokens_per_hour_limit = (project_settings.tokens_per_hour_limit or 0) if project_settings else 0
    daily_cost_budget_usd = (project_settings.daily_cost_budget_usd or 0.0) if project_settings else 0.0

    # Phase 4: usage repo for token tracking + rate limiting
    usage_repo = LLMUsageRepository(db)

    pa = PromptAssembly(agent, project, memory_content, prompt_overrides=prompt_overrides)
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
        project_model_overrides=model_overrides,
    )

    summarization_injected = False

    while iteration < MAX_ITERATIONS:
        if interrupt_flag():
            await session_service.end_session_force(session_id, "interrupted")
            return "interrupted"

        # Re-check for new human messages every MID_LOOP_MSG_CHECK_INTERVAL iterations.
        # This ensures the agent sees user input sent after the session started.
        if iteration > 0 and iteration % MID_LOOP_MSG_CHECK_INTERVAL == 0:
            mid_loop_unread = await message_service.get_unread_for_agent(agent.id)
            if mid_loop_unread:
                await message_service.mark_received([m.id for m in mid_loop_unread])
                mid_loop_text = PromptAssembly.format_incoming_messages(
                    mid_loop_unread, agent_by_id, USER_AGENT_ID
                )
                capped = pa._cap_incoming_messages(mid_loop_text)
                pa.messages.append({"role": "user", "content": capped})
                await agent_msg_repo.create_message(
                    agent_id=agent.id,
                    project_id=project.id,
                    role="user",
                    content=capped,
                    loop_iteration=iteration,
                    session_id=session_id,
                )
                logger.info(
                    "Agent %s mid-loop: injected %d new message(s) at iteration %d",
                    agent.id,
                    len(mid_loop_unread),
                    iteration,
                )

        # Inject summarization block when context pressure hits 70%
        if not summarization_injected and pa.context_pressure_ratio() >= 0.70:
            logger.info(
                "Agent %s context pressure %.0f%% — injecting summarization block",
                agent.id,
                pa.context_pressure_ratio() * 100,
            )
            pa.append_summarization()
            summarization_injected = True

        # ── Gate 1: daily token budget (hard stop) ─────────────────────
        if daily_token_budget > 0:
            tokens_today = await usage_repo.daily_tokens_for_project(project.id)
            if tokens_today >= daily_token_budget:
                logger.warning(
                    "Agent %s: daily token budget (%d) exhausted (%d used) — ending session",
                    agent.id, daily_token_budget, tokens_today,
                )
                await session_service.end_session_force(session_id, "budget_exhausted")
                await _send_fallback_message(
                    message_service, agent, project,
                    f"This project's daily token budget ({daily_token_budget:,} tokens) has been "
                    "reached. Agents will resume after midnight UTC.",
                    emit_agent_message,
                )
                return "budget_exhausted"

        # ── Gate 2: daily cost budget (hard stop) ───────────────────────
        if daily_cost_budget_usd > 0:
            cost_today = await usage_repo.daily_cost_usd_for_project(project.id)
            if cost_today >= daily_cost_budget_usd:
                logger.warning(
                    "Agent %s: daily cost budget ($%.4f) exhausted ($%.4f used) — ending session",
                    agent.id, daily_cost_budget_usd, cost_today,
                )
                await session_service.end_session_force(session_id, "cost_budget_exhausted")
                await _send_fallback_message(
                    message_service, agent, project,
                    f"This project's daily cost budget (${daily_cost_budget_usd:.2f}) has been "
                    f"reached (${cost_today:.4f} spent today). Agents will resume after midnight UTC.",
                    emit_agent_message,
                )
                return "cost_budget_exhausted"

        # ── Gate 3: hourly rate limits (soft pause — resumes when limits clear) ──
        if calls_per_hour_limit > 0 or tokens_per_hour_limit > 0:
            hourly = await usage_repo.hourly_stats(project.id)
            calls_over = calls_per_hour_limit > 0 and hourly["calls"] >= calls_per_hour_limit
            tokens_over = tokens_per_hour_limit > 0 and hourly["tokens"] >= tokens_per_hour_limit
            if calls_over or tokens_over:
                end_reason, fresh_limits = await _rate_limit_soft_pause(
                    usage_repo=usage_repo,
                    ps_repo=ps_repo,
                    project_id=project.id,
                    agent_id=agent.id,
                    interrupt_flag=interrupt_flag,
                )
                if end_reason == "interrupted":
                    await session_service.end_session_force(session_id, "interrupted")
                    return "interrupted"
                if end_reason == "rate_limited_timeout":
                    await session_service.end_session_force(session_id, "rate_limited_timeout")
                    await _send_fallback_message(
                        message_service, agent, project,
                        "The project's hourly rate limit was not cleared within 10 minutes. "
                        "Please raise the limit in Project Settings and send a new message.",
                        emit_agent_message,
                    )
                    return "rate_limited_timeout"
                # Limits cleared or relaxed — update local vars so remaining gates use fresh values
                if fresh_limits:
                    calls_per_hour_limit = fresh_limits.get("calls_per_hour_limit", calls_per_hour_limit)
                    tokens_per_hour_limit = fresh_limits.get("tokens_per_hour_limit", tokens_per_hour_limit)
                    daily_token_budget = fresh_limits.get("daily_token_budget", daily_token_budget)
                    daily_cost_budget_usd = fresh_limits.get("daily_cost_budget_usd", daily_cost_budget_usd)

        try:
            content, tool_calls, llm_response = await llm.chat_completion_with_tools(
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

        # Phase 4: record token usage + broadcast real-time usage event
        _effective_model = llm_response.model or resolved_model
        _effective_provider = llm_response.provider or "unknown"
        try:
            await usage_repo.record(
                project_id=project.id,
                agent_id=agent.id,
                session_id=session_id,
                provider=_effective_provider,
                model=_effective_model,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                request_id=llm_response.request_id,
            )
        except Exception as exc:
            logger.warning("Failed to record LLM usage event: %s", exc)

        try:
            _call_cost = estimate_cost_usd(
                _effective_model,
                llm_response.input_tokens,
                llm_response.output_tokens,
            )
            await ws_manager.broadcast_usage_update(
                project_id=project.id,
                agent_id=agent.id,
                model=_effective_model,
                provider=_effective_provider,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                estimated_cost_usd=round(_call_cost, 6),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.warning("Failed to broadcast usage_update event: %s", exc)

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
                validate_tool_input(name, tool_input)
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
