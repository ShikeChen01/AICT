"""Tool executors — messaging: send_message, broadcast_message."""

from __future__ import annotations

from backend.core.constants import USER_AGENT_ID
from backend.tools.base import RunContext, parse_tool_uuid


async def run_send_message(ctx: RunContext, tool_input: dict) -> str:
    from backend.workers.message_router import get_message_router

    target_agent_id = parse_tool_uuid(tool_input, "target_agent_id")
    msg = await ctx.message_service.send(
        from_agent_id=ctx.agent.id,
        target_agent_id=target_agent_id,
        project_id=ctx.project.id,
        content=str(tool_input["content"]),
    )
    await ctx.db.flush()
    if target_agent_id == USER_AGENT_ID:
        if ctx.emit_agent_message:
            ctx.emit_agent_message(msg)
    else:
        get_message_router().notify(target_agent_id)
    return f"Message sent to {target_agent_id}"


async def run_broadcast_message(ctx: RunContext, tool_input: dict) -> str:
    await ctx.message_service.broadcast(
        from_agent_id=ctx.agent.id,
        project_id=ctx.project.id,
        content=str(tool_input["content"]),
    )
    await ctx.db.flush()
    return "Broadcast sent."
