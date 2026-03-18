"""Tool executors — messaging: send_message, broadcast_message."""

from __future__ import annotations

from backend.tools.base import RunContext, parse_tool_uuid
from backend.tools.result import ToolExecutionError


async def run_send_message(ctx: RunContext, tool_input: dict) -> str:
    from backend.workers.message_router import get_message_router

    raw_agent = tool_input.get("target_agent_id")
    raw_user = tool_input.get("target_user_id")

    if raw_agent and raw_user:
        raise ToolExecutionError(
            "Provide exactly one of target_agent_id or target_user_id, not both.",
            error_code=ToolExecutionError.INVALID_INPUT,
        )
    if not raw_agent and not raw_user:
        raise ToolExecutionError(
            "Either target_agent_id or target_user_id is required.",
            error_code=ToolExecutionError.INVALID_INPUT,
        )

    content = str(tool_input["content"])

    if raw_user:
        # Agent → User
        target_user_id = parse_tool_uuid(tool_input, "target_user_id")
        msg = await ctx.message_service.send_agent_to_user(
            from_agent_id=ctx.agent.id,
            target_user_id=target_user_id,
            project_id=ctx.project.id,
            content=content,
        )
        await ctx.db.flush()
        if ctx.emit_agent_message:
            ctx.emit_agent_message(msg)
        return f"Message sent to user {target_user_id}"
    else:
        # Agent → Agent
        target_agent_id = parse_tool_uuid(tool_input, "target_agent_id")
        msg = await ctx.message_service.send(
            from_agent_id=ctx.agent.id,
            target_agent_id=target_agent_id,
            project_id=ctx.project.id,
            content=content,
        )
        await ctx.db.flush()
        get_message_router().notify(target_agent_id)
        return f"Message sent to agent {target_agent_id}"


async def run_broadcast_message(ctx: RunContext, tool_input: dict) -> str:
    await ctx.message_service.broadcast(
        from_agent_id=ctx.agent.id,
        project_id=ctx.project.id,
        content=str(tool_input["content"]),
    )
    await ctx.db.flush()
    return "Broadcast sent."
