"""Stateless helper functions for the Agent abstraction.

Extracted from the monolithic loop.py. These are pure utilities with no
dependency on Agent or _LoopState — they take explicit arguments and return
values.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent as AgentRecord, Task
from backend.db.repositories.messages import AgentMessageRepository
from backend.llm.contracts import ImagePart
from backend.prompts.assembly import PromptAssembly
from backend.logging.my_logger import get_logger

if TYPE_CHECKING:
    from backend.services.message_service import MessageService

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 1000
MAX_LOOPBACKS = 5
MID_LOOP_MSG_CHECK_INTERVAL = 5
RATE_LIMIT_POLL_SECONDS = 5
RATE_LIMIT_MAX_WAIT_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Vision helpers
# ---------------------------------------------------------------------------


def model_supports_vision(model: str) -> bool:
    """Return True if the model supports image inputs (catalog-driven)."""
    from backend.llm.model_catalog import model_supports_vision as _msv
    return _msv(model)


def get_max_images(agent: AgentRecord) -> int:
    """Return max images per turn for the agent (from token_allocations or default 10)."""
    alloc = getattr(agent, "token_allocations", None) or {}
    return int(alloc.get("max_images_per_turn", 10))


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def default_model_for_agent(agent: AgentRecord) -> str:
    """Return the config-default model for an agent whose DB model field is empty.

    Handles legacy agents created before the write-through migration.
    """
    from backend.config import settings
    role = (agent.role or "").lower()
    if role == "manager":
        return settings.manager_model_default
    if role == "cto":
        return settings.cto_model_default
    tier = (getattr(agent, "tier", None) or "junior").lower()
    if tier == "senior":
        return settings.engineer_senior_model
    if tier == "intermediate":
        return settings.engineer_intermediate_model
    return settings.engineer_junior_model


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------


async def send_fallback_message(
    message_service: "MessageService",
    agent: AgentRecord,
    project_id: UUID,
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
            project_id=project_id,
            content=content,
            message_type="system",
        )
        if emit_agent_message:
            emit_agent_message(msg)
    except Exception as exc:
        logger.warning("Failed to send fallback message for agent %s: %s", agent.id, exc)


async def assignment_message_for_agent(db: AsyncSession, agent: AgentRecord) -> str | None:
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


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


async def persist_tool_message(
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
    """Persist a single tool-result message to agent_messages.

    The content is truncated to MAX_TOOL_RESULT_HISTORY_CHARS because full
    tool results are ephemeral — only available in-memory for the next LLM
    iteration.  Persisted history stores a short summary; the agent is
    expected to save important data to memory or re-run the tool.
    """
    from backend.tools.base import truncate_for_history

    tool_input_stored = {"__tool_use_id__": tool_use_id, **tool_input}
    await agent_msg_repo.create_message(
        agent_id=agent_id,
        project_id=project_id,
        role="tool",
        content=truncate_for_history(result_text),
        loop_iteration=iteration,
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input_stored,
    )


# ---------------------------------------------------------------------------
# Rate-limit soft pause
# ---------------------------------------------------------------------------


async def rate_limit_soft_pause(
    *,
    usage_repo,
    ps_repo,
    project_id: UUID,
    agent_id: UUID,
    interrupt_flag: callable,
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

        fresh_ps = await ps_repo.get_by_project(project_id)
        calls_limit = (fresh_ps.calls_per_hour_limit or 0) if fresh_ps else 0
        tokens_limit = (fresh_ps.tokens_per_hour_limit or 0) if fresh_ps else 0

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

    return "rate_limited_timeout", {}


# ---------------------------------------------------------------------------
# Image attachment helpers
# ---------------------------------------------------------------------------


def attach_images_to_prompt(
    pa: PromptAssembly,
    unread: list,
    attachments_by_msg: dict,
    resolved_model: str,
    agent: AgentRecord,
) -> None:
    """Attach image parts from message attachments to the last user message in pa.messages."""
    all_image_parts: list[ImagePart] = []
    for msg in unread:
        for att in attachments_by_msg.get(msg.id, []):
            all_image_parts.append(ImagePart(data=att.data, media_type=att.mime_type))

    if not all_image_parts:
        return

    if model_supports_vision(resolved_model):
        max_imgs = get_max_images(agent)
        truncated_note = ""
        if len(all_image_parts) > max_imgs:
            excess = len(all_image_parts) - max_imgs
            all_image_parts = all_image_parts[:max_imgs]
            truncated_note = (
                f"\n[System: {excess} image(s) were dropped — "
                f"limit is {max_imgs} images per turn. "
                "Adjust the image cap in the Prompt Builder if needed.]"
            )
            logger.warning(
                "Agent %s: truncated image attachments from %d to %d (cap=%d)",
                agent.id, len(all_image_parts) + excess, max_imgs, max_imgs,
            )
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
