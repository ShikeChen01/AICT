"""Tool executors — tasks: list, get, create, assign, update, abort."""

from __future__ import annotations

from backend.core.constants import USER_AGENT_ID
from backend.schemas.task import TaskCreate
from backend.tools.base import RunContext, parse_tool_uuid
from backend.tools.result import ToolExecutionError


async def run_list_tasks(ctx: RunContext, tool_input: dict) -> str:
    status = tool_input.get("status")
    tasks = (
        await ctx.task_service.list_by_status(ctx.project.id, status)
        if status
        else await ctx.task_service.list_by_project(ctx.project.id)
    )
    return (
        "\n".join(
            f"{t.id} | [{t.status}] {t.title} | assigned={t.assigned_agent_id}"
            for t in tasks
        )
        or "No tasks. You can ask Manager for more tasks or end the session by using the 'end' tool."
    )


async def run_get_task_details(ctx: RunContext, tool_input: dict) -> str:
    task = await ctx.task_service.get(parse_tool_uuid(tool_input, "task_id"))
    return (
        f"id={task.id}\n"
        f"title={task.title}\n"
        f"description={task.description}\n"
        f"status={task.status}\n"
        f"assigned_agent_id={task.assigned_agent_id}\n"
        f"git_branch={task.git_branch}\n"
        f"pr_url={task.pr_url}"
    )


async def run_create_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise ToolExecutionError(
            "Only the manager can create tasks.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    task = await ctx.task_service.create(
        ctx.project.id,
        TaskCreate(
            title=str(tool_input["title"]),
            description=tool_input.get("description"),
            critical=int(tool_input.get("critical", 5)),
            urgent=int(tool_input.get("urgent", 5)),
            status="backlog",
        ),
        created_by_id=ctx.agent.id,
    )
    await ctx.db.flush()
    return f"Task created: {task.id}"


async def run_assign_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise ToolExecutionError(
            "Only the manager can assign tasks.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    task = await ctx.task_service.assign(
        parse_tool_uuid(tool_input, "task_id"),
        parse_tool_uuid(tool_input, "agent_id"),
    )
    await ctx.db.flush()
    return f"Task assigned: {task.id} -> {task.assigned_agent_id}"


async def run_update_task_status(ctx: RunContext, tool_input: dict) -> str:
    task = await ctx.task_service.get(parse_tool_uuid(tool_input, "task_id"))
    if ctx.agent.role == "engineer" and task.assigned_agent_id != ctx.agent.id:
        raise ToolExecutionError(
            "Engineers can only update tasks assigned to themselves.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
            hint="Use list_tasks to find tasks assigned to you.",
        )
    task = await ctx.task_service.update_status(task.id, str(tool_input["status"]))
    await ctx.db.flush()
    return f"Task status updated: {task.id} -> {task.status}"


async def run_abort_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "engineer":
        raise ToolExecutionError(
            "Only engineers can abort tasks.",
            error_code=ToolExecutionError.PERMISSION_DENIED,
        )
    if ctx.agent.current_task_id is None:
        raise ToolExecutionError(
            "No active task to abort.",
            error_code=ToolExecutionError.NOT_FOUND,
            hint="Use list_tasks to check your currently assigned tasks.",
        )
    task = await ctx.task_service.update_status(ctx.agent.current_task_id, "aborted")
    ctx.agent.current_task_id = None
    await ctx.message_service.send(
        from_agent_id=ctx.agent.id,
        target_agent_id=task.created_by_id or USER_AGENT_ID,
        project_id=ctx.project.id,
        content=f"Task '{task.title}' aborted: {tool_input.get('reason', '')}",
        message_type="system",
    )
    await ctx.db.flush()
    return "Task aborted."
