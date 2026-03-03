"""Universal per-agent loop with tool execution.

Design: "wake-to-END" loop. One agent wakes when it has unread channel messages (or an
assigned task with no unread). Each iteration: (1) optionally inject mid-loop messages,
(2) run budget/rate-limit gates, (3) call LLM with system prompt + conversation + tools,
(4) persist assistant message and optionally run tools, (5) append tool results to
conversation and loop, or handle END / loopback / error. Session ends when the agent
calls the "end" tool (normal_end), or on max_iterations, max_loopbacks, interrupt,
budget_exhausted, or LLM error. All agents (GM, CTO, Engineers) use this same loop;
behavior differs by role via prompt blocks and tool registry (get_tool_defs_for_role).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, PromptBlockConfig, Repository, Task
from backend.db.repositories.agent_templates import PromptBlockConfigRepository
from backend.db.repositories.attachments import AttachmentRepository
from backend.db.repositories.llm_usage import LLMUsageRepository
from backend.db.repositories.messages import AgentMessageRepository
from backend.db.repositories.project_secrets import ProjectSecretsRepository
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.llm.contracts import ImagePart
from backend.llm.model_resolver import resolve_provider
from backend.tools.executors.sandbox import ScreenshotResult
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
    get_thinking_phase_handlers,
    get_thinking_phase_tool_defs,
    get_tool_defs_for_agent,
    get_tool_defs_for_role,
    truncate_tool_output,
    validate_tool_input,
)
from backend.workers.message_router import get_message_router
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Vision and loop constants
# ---------------------------------------------------------------------------

def _model_supports_vision(model: str) -> bool:
    """Return True if the model supports image inputs (catalog-driven)."""
    from backend.llm.model_catalog import model_supports_vision
    return model_supports_vision(model)


def _get_max_images(agent: "Agent") -> int:
    """Return max images per turn for the agent (from token_allocations or default 10)."""
    alloc = getattr(agent, "token_allocations", None) or {}
    return int(alloc.get("max_images_per_turn", 10))


def _default_model_for_agent(agent: Agent) -> str:
    """Return the config-default model for an agent whose DB model field is empty.

    This handles legacy agents created before the write-through migration.
    """
    from backend.config import settings
    role = (agent.role or "").lower()
    if role == "manager":
        return settings.manager_model_default
    if role == "cto":
        return settings.cto_model_default
    # Engineer: resolve by tier/seniority
    tier = (getattr(agent, "tier", None) or "junior").lower()
    if tier == "senior":
        return settings.engineer_senior_model
    if tier == "intermediate":
        return settings.engineer_intermediate_model
    return settings.engineer_junior_model


# Safeguard: stop session after this many LLM turns (avoids runaway loops).
MAX_ITERATIONS = 1000
# If the agent replies with text only (no tool calls) this many times in a row, end session.
MAX_LOOPBACKS = 5
# Check for new human messages every N iterations so the agent sees late-sent user input.
MID_LOOP_MSG_CHECK_INTERVAL = 5
# Rate limit soft-pause: poll interval and maximum total wait before giving up.
RATE_LIMIT_POLL_SECONDS = 5
RATE_LIMIT_MAX_WAIT_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# _LoopState: mutable state bag for the main loop
# ---------------------------------------------------------------------------


@dataclass
class _LoopState:
    """Mutable state for a single agent session loop.

    Groups all state that ``run_inner_loop`` previously scattered across local variables.
    Extracted helpers read/write fields here instead of relying on closure captures.
    """
    # --- Prompt and tool context ---
    pa: PromptAssembly
    ctx: RunContext
    handlers: dict
    thinking_handlers: dict | None
    block_configs: list
    db_tool_defs: list
    resolved_model: str

    # --- Thinking phase ---
    thinking_enabled: bool
    thinking_stage: str | None  # None | "thinking" | "execution"

    # --- Summarization ---
    summarization_state: dict = field(default_factory=lambda: {"memory_injected": False, "history_injected": False})

    # --- Services / repos (session-scoped) ---
    agent: Agent = None  # type: ignore[assignment]
    project: Repository = None  # type: ignore[assignment]
    session_id: UUID = None  # type: ignore[assignment]
    db: AsyncSession = None  # type: ignore[assignment]
    agent_msg_repo: AgentMessageRepository = None  # type: ignore[assignment]
    message_service: MessageService = None  # type: ignore[assignment]
    session_service: SessionService = None  # type: ignore[assignment]
    usage_repo: LLMUsageRepository = None  # type: ignore[assignment]
    ps_repo: ProjectSettingsRepository = None  # type: ignore[assignment]
    llm: LLMService = None  # type: ignore[assignment]

    # --- Budget / rate-limit state (may be refreshed mid-session) ---
    daily_token_budget: int = 0
    daily_cost_budget_usd: float = 0.0
    calls_per_hour_limit: int = 0
    tokens_per_hour_limit: int = 0

    # --- Callbacks ---
    interrupt_flag: Callable[[], bool] = lambda: False
    emit_text: Callable[[str], None] | None = None
    emit_tool_call: Callable[[str, dict], None] | None = None
    emit_tool_result: Callable[[str, str], None] | None = None
    emit_agent_message: Callable[[object], None] | None = None

    # --- Agent roster for message formatting ---
    agent_by_id: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers: fallback message, assignment context, rate-limit pause
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Extracted helpers: message persistence, budget gates, image handling,
# mid-loop messages, thinking transition, END-solo warning, tool batch
# ---------------------------------------------------------------------------


async def _persist_tool_message(
    agent_msg_repo: AgentMessageRepository,
    agent_id: UUID,
    project_id: UUID,
    session_id: UUID,
    iteration: int,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict,
    result_text: str,
) -> None:
    """Persist a single tool-result message to agent_messages."""
    tool_input_stored = {"__tool_use_id__": tool_use_id, **tool_input}
    await agent_msg_repo.create_message(
        agent_id=agent_id,
        project_id=project_id,
        role="tool",
        content=result_text,
        loop_iteration=iteration,
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input_stored,
        tool_output=result_text,
    )


async def _check_budget_gates(
    state: _LoopState,
) -> str | None:
    """Check all budget/rate-limit gates before an LLM call.

    Returns an end-reason string if the session must stop, or None if all clear.
    When a rate-limit pause clears, refreshes the budget/limit fields on ``state``.
    """
    # Gate 1: daily token budget — hard stop
    if state.daily_token_budget > 0:
        tokens_today = await state.usage_repo.daily_tokens_for_project(state.project.id)
        if tokens_today >= state.daily_token_budget:
            logger.warning(
                "Agent %s: daily token budget (%d) exhausted (%d used) — ending session",
                state.agent.id, state.daily_token_budget, tokens_today,
            )
            await state.session_service.end_session_force(state.session_id, "budget_exhausted")
            await _send_fallback_message(
                state.message_service, state.agent, state.project,
                f"This project's daily token budget ({state.daily_token_budget:,} tokens) has been "
                "reached. Agents will resume after midnight UTC.",
                state.emit_agent_message,
            )
            return "budget_exhausted"

    # Gate 2: daily cost budget — hard stop
    if state.daily_cost_budget_usd > 0:
        cost_today = await state.usage_repo.daily_cost_usd_for_project(state.project.id)
        if cost_today >= state.daily_cost_budget_usd:
            logger.warning(
                "Agent %s: daily cost budget ($%.4f) exhausted ($%.4f used) — ending session",
                state.agent.id, state.daily_cost_budget_usd, cost_today,
            )
            await state.session_service.end_session_force(state.session_id, "cost_budget_exhausted")
            await _send_fallback_message(
                state.message_service, state.agent, state.project,
                f"This project's daily cost budget (${state.daily_cost_budget_usd:.2f}) has been "
                f"reached (${cost_today:.4f} spent today). Agents will resume after midnight UTC.",
                state.emit_agent_message,
            )
            return "cost_budget_exhausted"

    # Gate 3: hourly rate limits — soft pause
    if state.calls_per_hour_limit > 0 or state.tokens_per_hour_limit > 0:
        hourly = await state.usage_repo.hourly_stats(state.project.id)
        calls_over = state.calls_per_hour_limit > 0 and hourly["calls"] >= state.calls_per_hour_limit
        tokens_over = state.tokens_per_hour_limit > 0 and hourly["tokens"] >= state.tokens_per_hour_limit
        if calls_over or tokens_over:
            end_reason, fresh_limits = await _rate_limit_soft_pause(
                usage_repo=state.usage_repo,
                ps_repo=state.ps_repo,
                project_id=state.project.id,
                agent_id=state.agent.id,
                interrupt_flag=state.interrupt_flag,
            )
            if end_reason == "interrupted":
                await state.session_service.end_session_force(state.session_id, "interrupted")
                return "interrupted"
            if end_reason == "rate_limited_timeout":
                await state.session_service.end_session_force(state.session_id, "rate_limited_timeout")
                await _send_fallback_message(
                    state.message_service, state.agent, state.project,
                    "The project's hourly rate limit was not cleared within 10 minutes. "
                    "Please raise the limit in Project Settings and send a new message.",
                    state.emit_agent_message,
                )
                return "rate_limited_timeout"
            # Limits cleared or user relaxed them — refresh local limit vars
            if fresh_limits:
                state.calls_per_hour_limit = fresh_limits.get("calls_per_hour_limit", state.calls_per_hour_limit)
                state.tokens_per_hour_limit = fresh_limits.get("tokens_per_hour_limit", state.tokens_per_hour_limit)
                state.daily_token_budget = fresh_limits.get("daily_token_budget", state.daily_token_budget)
                state.daily_cost_budget_usd = fresh_limits.get("daily_cost_budget_usd", state.daily_cost_budget_usd)

    return None


def _attach_images_to_prompt(
    pa: PromptAssembly,
    unread: list,
    attachments_by_msg: dict,
    resolved_model: str,
    agent: Agent,
) -> None:
    """Attach image parts from message attachments to the last user message in pa.messages."""
    all_image_parts: list[ImagePart] = []
    for msg in unread:
        for att in attachments_by_msg.get(msg.id, []):
            all_image_parts.append(ImagePart(data=att.data, media_type=att.mime_type))

    if not all_image_parts:
        return

    if _model_supports_vision(resolved_model):
        max_images = _get_max_images(agent)
        truncated_note = ""
        if len(all_image_parts) > max_images:
            excess = len(all_image_parts) - max_images
            all_image_parts = all_image_parts[:max_images]
            truncated_note = (
                f"\n[System: {excess} image(s) were dropped — "
                f"limit is {max_images} images per turn. "
                "Adjust the image cap in the Prompt Builder if needed.]"
            )
            logger.warning(
                "Agent %s: truncated image attachments from %d to %d (cap=%d)",
                agent.id, len(all_image_parts) + excess, max_images, max_images,
            )
        # Find and patch the last user message with image parts.
        for _i in range(len(pa.messages) - 1, -1, -1):
            if pa.messages[_i].get("role") == "user":
                patched = {**pa.messages[_i], "image_parts": all_image_parts}
                if truncated_note:
                    patched["content"] = patched.get("content", "") + truncated_note
                pa.messages[_i] = patched
                break
        logger.info(
            "Agent %s: attached %d image part(s) from %d message attachment(s)",
            agent.id,
            len(all_image_parts),
            sum(len(v) for v in attachments_by_msg.values()),
        )
    else:
        # Model does not support vision: append a note so the agent knows.
        note = (
            f"\n[System: User attached {len(all_image_parts)} image(s) "
            f"but model '{resolved_model}' does not support vision. "
            "Ask the user to describe the image(s) in text.]"
        )
        for _i in range(len(pa.messages) - 1, -1, -1):
            if pa.messages[_i].get("role") == "user":
                pa.messages[_i] = {
                    **pa.messages[_i],
                    "content": pa.messages[_i].get("content", "") + note,
                }
                break
        logger.info(
            "Agent %s: model '%s' has no vision — injected vision-unavailable note",
            agent.id,
            resolved_model,
        )


async def _inject_mid_loop_messages(
    state: _LoopState,
    iteration: int,
) -> None:
    """Check for new channel messages mid-loop and inject them into the prompt."""
    mid_loop_unread = await state.message_service.get_unread_for_agent(state.agent.id)
    if not mid_loop_unread:
        return
    await state.message_service.mark_received([m.id for m in mid_loop_unread])
    mid_loop_text = PromptAssembly.format_incoming_messages(
        mid_loop_unread, state.agent_by_id, USER_AGENT_ID
    )
    capped = state.pa._cap_incoming_messages(mid_loop_text)
    state.pa.messages.append({"role": "user", "content": capped})
    await state.agent_msg_repo.create_message(
        agent_id=state.agent.id,
        project_id=state.project.id,
        role="user",
        content=capped,
        loop_iteration=iteration,
        session_id=state.session_id,
    )
    logger.info(
        "Agent %s mid-loop: injected %d new message(s) at iteration %d",
        state.agent.id,
        len(mid_loop_unread),
        iteration,
    )


def _check_and_inject_summarization(state: _LoopState) -> None:
    """Check each dynamic section independently and inject appropriate prompts."""
    triggered = state.pa.check_summarization_triggers()

    if "memory" in triggered and not state.summarization_state["memory_injected"]:
        logger.info(
            "Agent %s: memory pressure %.0f%% — injecting memory summarization",
            state.agent.id,
            (state.pa._memory_budget_tokens and
             len(state.pa._current_memory_content) // 4 / state.pa._memory_budget_tokens * 100) or 0,
        )
        _mem_content = next(
            (b.content for b in state.block_configs if b.block_key == "summarization_memory" and b.enabled),
            (
                "Your working memory is approaching its budget limit. Compress your memory "
                "using update_memory: merge related items, remove redundant entries, "
                "keep only actively relevant context. Call update_memory then continue your work."
            ),
        )
        state.pa.append_summarization(_mem_content)
        state.summarization_state["memory_injected"] = True

    if "current_session" in triggered and not state.summarization_state["history_injected"]:
        logger.info(
            "Agent %s: session pressure %.0f%% — injecting history summarization",
            state.agent.id,
            state.pa.context_pressure_ratio() * 100,
        )
        _hist_content = next(
            (b.content for b in state.block_configs if b.block_key == "summarization_history" and b.enabled),
            next(
                (b.content for b in state.block_configs if b.block_key == "summarization" and b.enabled),
                PromptAssembly.get_summarization_block(),
            ),
        )
        state.pa.append_summarization(_hist_content)
        state.summarization_state["history_injected"] = True


async def _handle_thinking_transition(
    thinking_done_call: dict,
    tool_calls: list[dict],
    state: _LoopState,
    iteration: int,
) -> list[dict]:
    """Process thinking_done tool call: persist result, rebuild prompt for Stage 2.

    Returns the tool_calls list with thinking_done calls removed.
    """
    td_id = thinking_done_call.get("id", "thinking-done-transition")
    td_summary = (thinking_done_call.get("input") or {}).get("summary", "Plan saved to memory.")
    result_text = f"Thinking phase complete. Transitioning to execution phase.\nPlan summary: {td_summary}"
    state.pa.append_tool_result("thinking_done", result_text, td_id)
    await _persist_tool_message(
        state.agent_msg_repo, state.agent.id, state.project.id,
        state.session_id, iteration, "thinking_done", td_id,
        thinking_done_call.get("input") or {}, result_text,
    )
    if state.emit_tool_result:
        state.emit_tool_result("thinking_done", result_text)

    # Rebuild system prompt for Stage 2 and switch to full (DB-customized) tool set.
    state.thinking_stage = "execution"
    memory_content_now = state.agent.memory
    if isinstance(memory_content_now, dict):
        import json as _json
        memory_content_now = _json.dumps(memory_content_now) if memory_content_now else None
    state.pa.rebuild_for_execution_stage(state.block_configs, memory_content_now)
    state.pa.tools = state.db_tool_defs
    logger.info("Agent %s: thinking_done called — entering Stage 2 (execution)", state.agent.id)

    # Remove thinking_done calls so we don't try to dispatch them in tool execution.
    return [tc for tc in tool_calls if tc.get("name") != "thinking_done"]


async def _handle_end_solo_warning(
    end_calls: list[dict],
    state: _LoopState,
    iteration: int,
) -> None:
    """Inject warning when END was called alongside other tools."""
    for ec in end_calls:
        end_use_id = ec.get("id") or "end-solo-rule"
        _end_solo_content = (
            "END was called alongside other tools in the same response and was ignored "
            "for this iteration. END must always be called alone. If you have remaining "
            "work, complete it first. Then call END by itself in a separate response."
        )
        state.pa.append_end_solo_warning(_end_solo_content, end_use_id)
        await _persist_tool_message(
            state.agent_msg_repo, state.agent.id, state.project.id,
            state.session_id, iteration, "end", end_use_id, {}, _end_solo_content,
        )


async def _execute_tool_batch(
    non_end_calls: list[dict],
    state: _LoopState,
    iteration: int,
) -> list[ImagePart]:
    """Execute all non-END tool calls, persist results, return pending screenshot parts."""
    active_handlers = (
        state.thinking_handlers
        if (state.thinking_enabled and state.thinking_stage == "thinking")
        else state.handlers
    )
    pending_screenshot_parts: list[ImagePart] = []

    for tc in non_end_calls:
        name = tc.get("name", "")
        tool_input = tc.get("input") or {}
        if state.emit_tool_call:
            state.emit_tool_call(name, tool_input)

        tool_use_id = tc.get("id", "")
        try:
            handler = active_handlers.get(name)
            if handler is None:
                raise RuntimeError(f"Unknown tool '{name}'")
            validate_tool_input(name, tool_input)
            raw_result = await handler(state.ctx, tool_input)
        except Exception as exc:
            result_text = truncate_tool_output(f"Tool '{name}' failed: {exc}")
            state.pa.append_tool_error(name, exc, tool_use_id)
            if state.emit_tool_result:
                state.emit_tool_result(name, result_text)
            await _persist_tool_message(
                state.agent_msg_repo, state.agent.id, state.project.id,
                state.session_id, iteration, name, tool_use_id, tool_input, result_text,
            )
            continue

        # Handle ScreenshotResult: inject image as vision content for the LLM.
        if isinstance(raw_result, ScreenshotResult):
            result_text = f"Screenshot captured ({len(raw_result.image_bytes)} bytes). The image is attached below for your inspection."
            if _model_supports_vision(state.resolved_model):
                pending_screenshot_parts.append(
                    ImagePart(data=raw_result.image_bytes, media_type=raw_result.media_type)
                )
            else:
                result_text += (
                    f"\n[Warning: model '{state.resolved_model}' does not support vision. "
                    "You cannot view the screenshot. Consider using a vision-capable model.]"
                )
        else:
            result_text = truncate_tool_output(raw_result)

        if state.emit_tool_result:
            state.emit_tool_result(name, result_text)
        state.pa.append_tool_result(name, result_text, tool_use_id)

        # Post-tool hooks for memory and history compaction
        if name == "update_memory":
            _enforce_memory_budget(state)

        if name == "compact_history":
            keep_recent = tool_input.get("keep_recent", 20)
            state.pa.compact_messages(keep_recent=keep_recent)
            state.summarization_state["history_injected"] = False

        await _persist_tool_message(
            state.agent_msg_repo, state.agent.id, state.project.id,
            state.session_id, iteration, name, tool_use_id, tool_input, result_text,
        )

    return pending_screenshot_parts


def _enforce_memory_budget(state: _LoopState) -> None:
    """Enforce memory budget after an update_memory call and refresh the system prompt."""
    _raw_memory = state.agent.memory
    if isinstance(_raw_memory, dict):
        _mem_str = _raw_memory.get("content", "") if _raw_memory else ""
    elif isinstance(_raw_memory, str):
        _mem_str = _raw_memory
    else:
        _mem_str = ""

    _mem_budget_chars = state.pa._memory_budget_chars
    if len(_mem_str) > _mem_budget_chars:
        _mem_str = _mem_str[:_mem_budget_chars] + "\n[Memory truncated to budget limit]"
        state.agent.memory = {"content": _mem_str}
        # Note: db.flush() is not called here; the caller's session handles it.
        logger.warning(
            "Agent %s: memory exceeded budget (%d chars) — truncated to %d chars",
            state.agent.id,
            len(_mem_str),
            _mem_budget_chars,
        )

    _mem_now = state.agent.memory
    if isinstance(_mem_now, dict):
        import json as _json_mem2
        _mem_now = _json_mem2.dumps(_mem_now) if _mem_now else None
    state.pa._refresh_memory_in_system_prompt(
        _mem_now, state.block_configs, state.thinking_stage
    )
    # Allow re-trigger on next iteration (pressure may still be high)
    state.summarization_state["memory_injected"] = False


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


async def _bootstrap_session(
    agent: Agent,
    project: Repository,
    session_id: UUID,
    trigger_message_id: UUID | None,
    *,
    db: AsyncSession,
    interrupt_flag: Callable[[], bool],
    emit_text: Callable[[str], None] | None = None,
    emit_tool_call: Callable[[str, dict], None] | None = None,
    emit_tool_result: Callable[[str, str], None] | None = None,
    emit_agent_message: Callable[[object], None] | None = None,
) -> tuple[_LoopState | None, str | None]:
    """One-time session setup.

    Returns (state, early_exit_reason).
    If early_exit_reason is not None, caller should return it immediately.
    """
    # --- Services and repos used for the whole session ---
    message_service = MessageService(db)
    session_service = SessionService(db)
    task_service = TaskService(db)
    agent_service = AgentService(db)
    agent_msg_repo = AgentMessageRepository(db)
    block_repo = PromptBlockConfigRepository(db)
    llm = LLMService()
    handlers = get_handlers_for_role(agent.role)

    # --- Session bootstrap: require either unread messages or an assigned task ---
    unread = await message_service.get_unread_for_agent(agent.id)
    assignment_context = None
    if not unread:
        assignment_context = await _assignment_message_for_agent(db, agent)
        if not assignment_context:
            await session_service.end_session(session_id, end_reason="normal_end", status="completed")
            return None, "normal_end"
    else:
        await message_service.mark_received([m.id for m in unread])

    result = await db.execute(select(Agent).where(Agent.project_id == project.id))
    project_agents = list(result.scalars().all())
    agent_by_id = {a.id: a for a in project_agents}

    # Format unread channel messages (or assignment context) as the "incoming" user text.
    new_messages_text = PromptAssembly.format_incoming_messages(
        unread, agent_by_id, USER_AGENT_ID, assignment_context,
    )

    # Load image attachments for unread messages (if any).
    _attachment_repo = AttachmentRepository(db)
    _unread_ids = [m.id for m in unread if m.id is not None]
    _attachments_by_msg = await _attachment_repo.get_for_messages(_unread_ids)

    memory_content = agent.memory
    if isinstance(memory_content, dict):
        import json as _json_mem
        memory_content = _json_mem.dumps(memory_content) if memory_content else None

    # Load project-level settings: budget/rate limits.
    ps_repo = ProjectSettingsRepository(db)
    project_settings = await ps_repo.get_by_project(project.id)
    daily_token_budget = (project_settings.daily_token_budget or 0) if project_settings else 0
    calls_per_hour_limit = (project_settings.calls_per_hour_limit or 0) if project_settings else 0
    tokens_per_hour_limit = (project_settings.tokens_per_hour_limit or 0) if project_settings else 0
    daily_cost_budget_usd = (project_settings.daily_cost_budget_usd or 0.0) if project_settings else 0.0

    # Load project secrets for agent injection (e.g. API keys)
    from backend.config import settings as app_settings
    secrets_repo = ProjectSecretsRepository(db, encryption_key=app_settings.secret_encryption_key)
    project_secrets = await secrets_repo.get_plaintext_values(project.id)

    usage_repo = LLMUsageRepository(db)

    # Read model from DB (write-through). Fall back to config defaults for legacy agents.
    resolved_model = agent.model or _default_model_for_agent(agent)
    resolved_provider = resolve_provider(agent.provider, resolved_model)

    # Determine thinking stage.
    thinking_enabled = getattr(agent, "thinking_enabled", False)
    thinking_stage: str | None = "thinking" if thinking_enabled else None

    # Load prompt block configs for this agent from DB.
    block_configs: list[PromptBlockConfig] = await block_repo.list_for_agent(agent.id)

    # Load DB-customized tool defs for this agent.
    db_tool_defs = await get_tool_defs_for_agent(agent.id, agent.role, db)

    # Build prompt: system blocks from DB + tool defs.
    if thinking_enabled:
        pa = PromptAssembly(
            agent, project, memory_content,
            block_configs=block_configs,
            model=resolved_model,
            thinking_stage="thinking",
            project_secrets=project_secrets,
        )
        pa.tools = get_thinking_phase_tool_defs(agent.role)
        thinking_handlers = get_thinking_phase_handlers()
        logger.info("Agent %s: thinking_enabled=True — starting Stage 1 (thinking)", agent.id)
    else:
        pa = PromptAssembly(
            agent, project, memory_content,
            block_configs=block_configs,
            model=resolved_model,
            thinking_stage=None,
            project_secrets=project_secrets,
        )
        pa.tools = db_tool_defs
        thinking_handlers = None

    # Load history in two phases: past sessions (budget-fitted) and current session (full).
    past_session_msgs = await agent_msg_repo.list_past_session_history(
        agent.id, session_id,
        budget_tokens=pa._past_session_budget_tokens,
    )
    current_session_msgs = await agent_msg_repo.list_current_session(
        agent.id, session_id,
    )

    pa.load_history(
        past_session_msgs,
        current_session_msgs,
        new_messages_text,
        known_tool_names=set(handlers.keys()) | {"thinking_done", "compact_history"},
    )

    # Attach images from message attachments.
    if _attachments_by_msg and new_messages_text:
        _attach_images_to_prompt(pa, unread, _attachments_by_msg, resolved_model, agent)

    # Persist the initial user turn to agent_messages so it appears in history on next load.
    if new_messages_text:
        await agent_msg_repo.create_message(
            agent_id=agent.id,
            project_id=project.id,
            role="user",
            content=new_messages_text,
            loop_iteration=0,
            session_id=session_id,
        )

    # RunContext is passed to every tool handler.
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

    state = _LoopState(
        pa=pa,
        ctx=ctx,
        handlers=handlers,
        thinking_handlers=thinking_handlers,
        block_configs=block_configs,
        db_tool_defs=db_tool_defs,
        resolved_model=resolved_model,
        thinking_enabled=thinking_enabled,
        thinking_stage=thinking_stage,
        agent=agent,
        project=project,
        session_id=session_id,
        db=db,
        agent_msg_repo=agent_msg_repo,
        message_service=message_service,
        session_service=session_service,
        usage_repo=usage_repo,
        ps_repo=ps_repo,
        llm=llm,
        daily_token_budget=daily_token_budget,
        daily_cost_budget_usd=daily_cost_budget_usd,
        calls_per_hour_limit=calls_per_hour_limit,
        tokens_per_hour_limit=tokens_per_hour_limit,
        interrupt_flag=interrupt_flag,
        emit_text=emit_text,
        emit_tool_call=emit_tool_call,
        emit_tool_result=emit_tool_result,
        emit_agent_message=emit_agent_message,
        agent_by_id=agent_by_id,
    )

    logger.info(
        "Agent %s (%s) session %s started: unread=%d",
        agent.id,
        agent.role,
        session_id,
        len(unread),
    )

    return state, None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


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
    """Run wake-to-END loop for one agent session.

    Returns an end reason string: "normal_end", "interrupted", "max_iterations",
    "max_loopbacks", "budget_exhausted", "cost_budget_exhausted", "rate_limited_timeout",
    or "error".
    """
    from backend.config import settings as app_settings

    state, early_exit = await _bootstrap_session(
        agent, project, session_id, trigger_message_id,
        db=db,
        interrupt_flag=interrupt_flag,
        emit_text=emit_text,
        emit_tool_call=emit_tool_call,
        emit_tool_result=emit_tool_result,
        emit_agent_message=emit_agent_message,
    )
    if early_exit:
        return early_exit

    # Check summarization at session start (loaded history may already be near budget)
    _check_and_inject_summarization(state)

    iteration = 0
    loopbacks = 0

    # ========== Main loop: each iteration = one LLM call, then optional tool execution ==========
    while iteration < MAX_ITERATIONS:
        if state.interrupt_flag():
            await state.session_service.end_session_force(state.session_id, "interrupted")
            return "interrupted"

        # Mid-loop: periodically pull new channel messages so the agent sees late-sent user input.
        if iteration > 0 and iteration % MID_LOOP_MSG_CHECK_INTERVAL == 0:
            await _inject_mid_loop_messages(state, iteration)

        # Check each dynamic section independently for summarization pressure (70% threshold)
        _check_and_inject_summarization(state)

        # Budget/rate-limit gates (checked before each LLM call)
        gate_result = await _check_budget_gates(state)
        if gate_result is not None:
            return gate_result

        # --- Call LLM with full context ---
        try:
            content, tool_calls, llm_response = await state.llm.chat_completion_with_tools(
                model=state.resolved_model,
                system_prompt=state.pa.system_prompt,
                messages=state.pa.messages,
                tools=state.pa.tools,
                max_tokens=app_settings.llm_max_tokens_agent_loop,
            )
        except Exception as exc:
            logger.exception("LLM call failed for agent %s: %s", state.agent.id, exc)
            await state.session_service.end_session_error(state.session_id)
            await _send_fallback_message(
                state.message_service,
                state.agent,
                state.project,
                f"I encountered an error processing your request and could not respond. "
                f"Error: {type(exc).__name__}: {str(exc)[:200]}",
                state.emit_agent_message,
            )
            return "error"

        # Record token usage and broadcast usage event
        _effective_model = llm_response.model or state.resolved_model
        _effective_provider = llm_response.provider or "unknown"
        try:
            await state.usage_repo.record(
                project_id=state.project.id,
                agent_id=state.agent.id,
                session_id=state.session_id,
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
                project_id=state.project.id,
                agent_id=state.agent.id,
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
        await state.session_service.increment_iteration(state.session_id)

        # Persist assistant turn (text + tool_calls) and append to prompt for next round.
        assistant_tool_input = {"__tool_calls__": tool_calls} if tool_calls else None
        await state.agent_msg_repo.create_message(
            agent_id=state.agent.id,
            project_id=state.project.id,
            role="assistant",
            content=content or "",
            loop_iteration=iteration,
            session_id=state.session_id,
            tool_input=assistant_tool_input,
        )
        if content and state.emit_text:
            state.emit_text(content)
        state.pa.append_assistant(content or "", tool_calls)

        # --- No tool calls: agent replied with text only ---
        if not tool_calls:
            loopbacks += 1
            if loopbacks >= MAX_LOOPBACKS:
                logger.warning(
                    "Agent %s hit max_loopbacks (%d) in session %s",
                    state.agent.id,
                    MAX_LOOPBACKS,
                    state.session_id,
                )
                await state.session_service.end_session_force(state.session_id, "max_loopbacks")
                await _send_fallback_message(
                    state.message_service,
                    state.agent,
                    state.project,
                    "I was unable to produce a valid response after several attempts. "
                    "Please try rephrasing your request.",
                    state.emit_agent_message,
                )
                return "max_loopbacks"
            _loopback_content = next(
                (b.content for b in block_configs if b.block_key == "loopback" and b.enabled),
                "You responded without calling any tools. This counts as a failed attempt. "
                "Your next response MUST include at least one tool call. "
                "If your work is complete, call END. If there is more to do, call the appropriate tool(s). "
                "Do NOT reply with only text. Act now — call a tool in this response.",
            )
            state.pa.append_loopback(_loopback_content)
            continue

        loopbacks = 0

        # --- thinking_done handling: stage transition (Stage 1 → Stage 2) ---
        thinking_done_calls = [tc for tc in tool_calls if tc.get("name") == "thinking_done"]
        if thinking_done_calls and state.thinking_enabled and state.thinking_stage == "thinking":
            tool_calls = await _handle_thinking_transition(
                thinking_done_calls[0], tool_calls, state, iteration,
            )
            if not tool_calls:
                continue

        # Rule: END must be called alone.
        end_calls = [tc for tc in tool_calls if tc.get("name") == "end"]
        non_end_calls = [tc for tc in tool_calls if tc.get("name") not in ("end", "thinking_done")]
        if end_calls and non_end_calls:
            await _handle_end_solo_warning(end_calls, state, iteration)

        # --- Execute each non-END tool ---
        if non_end_calls:
            pending_screenshot_parts = await _execute_tool_batch(non_end_calls, state, iteration)

            # After processing all tool calls, inject any pending screenshot images.
            if pending_screenshot_parts:
                for _i in range(len(state.pa.messages) - 1, -1, -1):
                    if state.pa.messages[_i].get("role") == "tool":
                        state.pa.messages[_i]["image_parts"] = pending_screenshot_parts
                        break
                logger.info(
                    "Agent %s: injected %d screenshot image_part(s) into conversation",
                    state.agent.id,
                    len(pending_screenshot_parts),
                )

        # --- Agent called only END: end session normally ---
        if end_calls and not non_end_calls:
            end_text = "Session ended."
            if state.emit_tool_result:
                state.emit_tool_result("end", end_text)
            await _persist_tool_message(
                state.agent_msg_repo, state.agent.id, state.project.id,
                state.session_id, iteration, "end", "", {}, end_text,
            )
            await state.session_service.end_session(state.session_id, end_reason="normal_end", status="completed")
            return "normal_end"

    # Fell through: hit MAX_ITERATIONS (safeguard).
    logger.warning(
        "Agent %s hit max_iterations (%d) in session %s",
        state.agent.id,
        MAX_ITERATIONS,
        state.session_id,
    )
    await state.session_service.end_session_force(state.session_id, "max_iterations")
    await _send_fallback_message(
        state.message_service,
        state.agent,
        state.project,
        "My session exceeded the maximum number of iterations and was ended automatically. "
        "Please send a new message to continue.",
        state.emit_agent_message,
    )
    return "max_iterations"
