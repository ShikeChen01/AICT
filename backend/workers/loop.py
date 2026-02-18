"""
Universal agent loop: inner loop logic shared by all agents.

Per docs/ideas.md Pillar 2: one loop for GM, CTO, Engineers.
Reads new messages from DB, assembles prompt, calls LLM, handles tool calls (END solo rule),
persists to agent_messages, session create/end via session_service.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, Repository
from backend.db.repositories.messages import AgentMessageRepository
from backend.services.message_service import MessageService
from backend.services.prompt_service import build_system_prompt, get_loopback_block
from backend.services.session_service import SessionService
from backend.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# END tool schema for the loop (solo call breaks the loop)
END_TOOL = {
    "name": "end",
    "description": "Signal that you have completed your current work. Call this ALONE when done. END puts you to sleep until a new message arrives. Never call END alongside other tools.",
    "input_schema": {"type": "object", "properties": {}},
}

MAX_ITERATIONS = 50
MAX_LOOPBACKS = 3


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
    emit_agent_message: callable[[str], None] | None = None,
) -> str:
    """
    Run one inner loop (wake-to-END) for the agent.
    Returns end_reason: normal_end | max_iterations | max_loopbacks | interrupted | error.
    """
    message_service = MessageService(db)
    session_service = SessionService(db)
    agent_msg_repo = AgentMessageRepository(db)
    llm = LLMService()

    # 1. Get unread channel messages for this agent
    unread = await message_service.get_unread_for_agent(agent.id)
    if not unread:
        # No new messages — should not happen when woken by router; safe to end
        await session_service.end_session(session_id, end_reason="normal_end", status="completed")
        return "normal_end"

    message_ids = [m.id for m in unread]
    await message_service.mark_received(message_ids)

    # Format new messages as user-role lines (for prompt)
    from backend.db.repositories.agents import AgentRepository
    agent_repo = AgentRepository(db)
    project_agents = await agent_repo.list_by_project(project.id)
    agent_by_id = {a.id: a for a in project_agents}

    def sender_name(aid: UUID | None) -> str:
        if aid is None:
            return "System"
        if aid == USER_AGENT_ID:
            return "User"
        a = agent_by_id.get(aid)
        return a.display_name if a else str(aid)

    new_messages_text = "\n".join(
        f"[Message from {sender_name(m.from_agent_id)}]: {m.content}" for m in unread
    )
    if new_messages_text:
        new_messages_text = new_messages_text.strip()

    # 2. Load existing conversation for this session
    history = await agent_msg_repo.list_by_session(session_id, limit=500)
    memory_content = agent.memory
    if isinstance(memory_content, dict):
        memory_content = str(memory_content) if memory_content else None
    system_prompt = build_system_prompt(agent, project, memory_content)

    # Build messages for LLM: history (user/assistant/tool) + new channel messages as user
    messages: list[dict] = []
    for h in history:
        role = h.role
        content = h.content or ""
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
        elif role == "tool":
            # AgentMessage has no tool_use_id; use tool_name as fallback for LLM correlation
            tool_use_id = getattr(h, "tool_use_id", None) or (h.tool_name or "")
            messages.append({
                "role": "tool",
                "content": content,
                "tool_use_id": tool_use_id,
            })
    if new_messages_text:
        messages.append({"role": "user", "content": new_messages_text})

    iteration = len([m for m in history if m.role == "assistant"])  # approximate
    loopbacks = 0
    tools = [END_TOOL]

    while iteration < MAX_ITERATIONS:
        if interrupt_flag():
            await session_service.end_session_force(session_id, "interrupted")
            return "interrupted"

        try:
            content, tool_calls = await llm.chat_completion_with_tools(
                model=agent.model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
            )
        except Exception as e:
            logger.exception("LLM call failed for agent %s: %s", agent.id, e)
            await session_service.end_session_error(session_id)
            return "error"

        await session_service.increment_iteration(session_id)
        iteration += 1

        # Persist assistant message
        await agent_msg_repo.create_message(
            agent_id=agent.id,
            project_id=project.id,
            role="assistant",
            content=content or "",
            loop_iteration=iteration,
            session_id=session_id,
        )
        if content and emit_text:
            emit_text(content)
        if tool_calls and emit_tool_call:
            for tc in tool_calls:
                emit_tool_call(tc.get("name", ""), tc.get("input") or {})

        # END solo rule: if only tool call is "end", break
        if tool_calls:
            names = [t.get("name") for t in tool_calls]
            if names == ["end"]:
                # Persist tool result for end (optional)
                await agent_msg_repo.create_message(
                    agent_id=agent.id,
                    project_id=project.id,
                    role="tool",
                    content="Session ended.",
                    loop_iteration=iteration,
                    session_id=session_id,
                    tool_name="end",
                    tool_input={},
                    tool_output="Session ended.",
                )
                if emit_tool_result:
                    emit_tool_result("end", "Session ended.")
                await session_service.end_session(session_id, end_reason="normal_end", status="completed")
                return "normal_end"
            # Other tools: for now we only have end; if LLM returns something else, inject error and continue
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                name = tc.get("name", "")
                if name != "end":
                    result = f"Tool '{name}' is not yet implemented. Call END when done."
                    if emit_tool_result:
                        emit_tool_result(name, result)
                    messages.append({"role": "tool", "content": result, "tool_use_id": tc.get("id", "")})
                    await agent_msg_repo.create_message(
                        agent_id=agent.id,
                        project_id=project.id,
                        role="tool",
                        content=result,
                        loop_iteration=iteration,
                        session_id=session_id,
                        tool_name=name,
                        tool_input=tc.get("input"),
                        tool_output=result,
                    )
        else:
            # No tool calls — loopback
            loopbacks += 1
            if loopbacks >= MAX_LOOPBACKS:
                await session_service.end_session_force(session_id, "max_loopbacks")
                return "max_loopbacks"
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": get_loopback_block()})

    await session_service.end_session_force(session_id, "max_iterations")
    return "max_iterations"
