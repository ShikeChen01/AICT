"""Backward-compatibility shim for the universal agent loop.

The Agent abstraction has moved to backend/agents/agent.py.
This module is kept so existing imports (tests, external callers) continue
to work without modification.

New code should import from backend.agents directly:
    from backend.agents import Agent, EmitCallbacks

This shim:
- Re-exports run_inner_loop() as a thin wrapper around Agent.run()
- Re-exports helper functions that tests import (_assignment_message_for_agent, etc.)
- Re-exports constants (MAX_ITERATIONS, MAX_LOOPBACKS, etc.)
- Keeps _LoopState as a tombstone dataclass for import-time compatibility
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.agent import Agent, EmitCallbacks
from backend.agents.helpers import (
    MAX_ITERATIONS,
    MAX_LOOPBACKS,
    MID_LOOP_MSG_CHECK_INTERVAL,
    RATE_LIMIT_POLL_SECONDS,
    RATE_LIMIT_MAX_WAIT_SECONDS,
    assignment_message_for_agent,
    attach_images_to_prompt,
    default_model_for_agent,
    model_supports_vision,
    persist_tool_message,
    rate_limit_soft_pause,
    send_fallback_message,
)
from backend.db.models import Agent as AgentRecord, Repository
from backend.logging.my_logger import get_logger

# Re-export helpers under their old underscore-prefixed names for test compat
_assignment_message_for_agent = assignment_message_for_agent
_attach_images_to_prompt = attach_images_to_prompt
_default_model_for_agent = default_model_for_agent
_model_supports_vision = model_supports_vision
_persist_tool_message = persist_tool_message
_rate_limit_soft_pause = rate_limit_soft_pause
_send_fallback_message = send_fallback_message

logger = get_logger(__name__)

__all__ = [
    "run_inner_loop",
    "MAX_ITERATIONS",
    "MAX_LOOPBACKS",
    "MID_LOOP_MSG_CHECK_INTERVAL",
    "_assignment_message_for_agent",
]


async def run_inner_loop(
    agent: AgentRecord,
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
) -> str:
    """Backward-compat wrapper: constructs Agent and delegates to Agent.run().

    Preserved for tests and any external callers that import run_inner_loop
    directly. New code should use Agent.run() instead.
    """
    callbacks = EmitCallbacks(
        emit_text=emit_text,
        emit_tool_call=emit_tool_call,
        emit_tool_result=emit_tool_result,
        emit_agent_message=emit_agent_message,
    )
    agent_instance = Agent(
        record=agent,
        project=project,
        db=db,
        callbacks=callbacks,
        interrupt_flag=interrupt_flag,
    )
    return await agent_instance.run(session_id, trigger_message_id)
