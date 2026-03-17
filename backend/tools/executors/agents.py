"""Tool executors — agent management: spawn, list, remove, interrupt."""

from __future__ import annotations

from sqlalchemy import select

from backend.db.models import Agent
from backend.tools.base import RunContext, parse_tool_uuid
from backend.tools.result import ToolExecutionError
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


async def run_spawn_engineer(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"manager", "cto"}:
        raise ToolExecutionError(
            "Only the manager or CTO can spawn engineers.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    engineer = await ctx.agent_service.spawn_engineer(
        ctx.project.id,
        display_name=str(tool_input["display_name"]),
        seniority=str(tool_input["seniority"]) if tool_input.get("seniority") else None,
    )
    await ctx.db.flush()
    from backend.workers.message_router import get_message_router
    from backend.workers.worker_manager import get_worker_manager

    await get_worker_manager().spawn_worker(engineer.id, engineer.project_id)
    get_message_router().notify(engineer.id)
    return (
        f"Engineer spawned: {engineer.id}\n"
        f"The engineer is now awake. Send it a message or assign a task to give it work."
    )


async def run_list_agents(ctx: RunContext, tool_input: dict) -> str:
    res = await ctx.db.execute(select(Agent).where(Agent.project_id == ctx.project.id))
    rows = list(res.scalars().all())
    return "\n".join(f"{a.id} | {a.display_name} | {a.role} | {a.status}" for a in rows)


async def run_remove_agent(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise ToolExecutionError(
            "Only the manager can remove agents.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    target_id = parse_tool_uuid(tool_input, "agent_id")
    reason = str(tool_input.get("reason", "")).strip()

    res = await ctx.db.execute(select(Agent).where(Agent.id == target_id))
    target = res.scalar_one_or_none()
    if target is None:
        raise ToolExecutionError(
            f"Agent {target_id} not found.",
            error_code=ToolExecutionError.NOT_FOUND,
            hint="Use list_agents to find valid agent UUIDs.",
        )
    if target.project_id != ctx.project.id:
        raise ToolExecutionError(
            "Cannot remove an agent from a different project.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    if target.role in ("manager", "cto"):
        raise ToolExecutionError(
            f"Cannot remove a {target.role} — only engineers can be removed.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )

    display_name = target.display_name

    if target.sandbox:
        try:
            from backend.services.sandbox_service import SandboxService
            await SandboxService().release_agent_sandbox(ctx.db, target)
        except Exception as exc:
            logger.warning("Failed to release sandbox for agent %s: %s", target_id, exc)

    from backend.workers.worker_manager import get_worker_manager
    await get_worker_manager().remove_worker(target_id)

    await ctx.agent_service.remove_agent(target_id, ctx.project.id)
    await ctx.db.flush()

    logger.info(
        "Manager %s removed agent %s (%s).%s",
        ctx.agent.id, target_id, display_name,
        f" Reason: {reason}" if reason else "",
    )
    return (
        f"Agent '{display_name}' ({target_id}) has been permanently removed from the project."
        + (f" Reason: {reason}" if reason else "")
    )


async def run_interrupt_agent(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"manager", "cto"}:
        raise ToolExecutionError(
            "Only the manager or CTO can interrupt agents.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    from backend.workers.worker_manager import get_worker_manager

    target_id = parse_tool_uuid(tool_input, "target_agent_id")
    get_worker_manager().interrupt_agent(target_id)
    return f"Interrupted agent {target_id}"
