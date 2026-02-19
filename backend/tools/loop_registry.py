"""Tool registry for the universal agent loop.

Defines RunContext (injected into every tool executor), LoopTool (wrapper
carrying name, schema, allowed roles, and executor), all executor functions,
and helpers to derive tool defs / handler maps by agent role.

Tool metadata (name, description, schema, roles) lives in tool_descriptions.json.
Adding a new tool: add an entry there, write an executor here, map it in _TOOL_EXECUTORS.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent, AgentMessage, Repository
from backend.db.repositories.messages import AgentMessageRepository
from backend.schemas.task import TaskCreate
from backend.services.agent_service import AgentService
from backend.services.e2b_service import E2BService, LOCAL_FALLBACK_SANDBOX_ERROR
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

try:
    from e2b import AsyncSandbox
except Exception:  # pragma: no cover - optional dependency
    AsyncSandbox = None

MAX_TOOL_RESULT_CHARS = 12000

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def truncate_tool_output(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "\n[output truncated]"


def parse_tool_uuid(tool_input: dict, field_name: str, *, required: bool = True) -> UUID | None:
    raw_value = tool_input.get(field_name)
    if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
        if required:
            raise RuntimeError(f"Invalid tool input: '{field_name}' is required and must be a UUID.")
        return None
    try:
        return UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(f"Invalid UUID for '{field_name}': {raw_value!r}") from exc


def is_local_fallback_sandbox(sandbox_id: str | None) -> bool:
    return bool(sandbox_id and sandbox_id.startswith("local-sbox-"))


# ---------------------------------------------------------------------------
# Runtime context
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    """Runtime context injected into every tool executor for a single agent session."""

    db: AsyncSession
    agent: Agent
    project: Repository
    session_id: UUID
    message_service: MessageService
    session_service: SessionService
    task_service: TaskService
    agent_service: AgentService
    agent_msg_repo: AgentMessageRepository
    emit_agent_message: Callable[[object], None] | None = field(default=None)


# ---------------------------------------------------------------------------
# Tool wrapper type
# ---------------------------------------------------------------------------

ToolExecutor = Callable[[RunContext, dict], Awaitable[str]]


@dataclass
class LoopTool:
    """Descriptor for a single loop tool.

    allowed_roles: list of role strings, or ["*"] to grant to all roles.
    execute: None for the special 'end' tool, which the loop handles separately.
    """

    name: str
    description: str
    input_schema: dict
    allowed_roles: list[str]
    execute: ToolExecutor | None = field(default=None)


# ---------------------------------------------------------------------------
# Tool executors — one function per tool
# ---------------------------------------------------------------------------


async def _run_notify_user(ctx: RunContext, tool_input: dict) -> str:
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


async def _run_broadcast_message(ctx: RunContext, tool_input: dict) -> str:
    await ctx.message_service.broadcast(
        from_agent_id=ctx.agent.id,
        project_id=ctx.project.id,
        content=str(tool_input["content"]),
    )
    await ctx.db.flush()
    return "Broadcast sent."


async def _run_update_memory(ctx: RunContext, tool_input: dict) -> str:
    ctx.agent.memory = {"content": str(tool_input["content"])}
    await ctx.db.flush()
    return "Memory updated."


async def _run_read_history(ctx: RunContext, tool_input: dict) -> str:
    limit = int(tool_input.get("limit", 20))
    offset = int(tool_input.get("offset", 0))
    session_filter = parse_tool_uuid(tool_input, "session_id", required=False)
    q = (
        select(AgentMessage)
        .where(AgentMessage.agent_id == ctx.agent.id)
        .order_by(AgentMessage.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if session_filter is not None:
        q = q.where(AgentMessage.session_id == session_filter)
    res = await ctx.db.execute(q)
    rows = list(res.scalars().all())
    return "\n".join(f"[{m.role}] {m.content}" for m in rows) or "No history."


async def _run_sleep(ctx: RunContext, tool_input: dict) -> str:
    duration = max(0, min(int(tool_input.get("duration_seconds", 0)), 3600))
    await asyncio.sleep(duration)
    return f"Slept for {duration} seconds."


async def _run_list_tasks(ctx: RunContext, tool_input: dict) -> str:
    status = tool_input.get("status")
    tasks = (
        await ctx.task_service.list_by_status(ctx.project.id, status)
        if status
        else await ctx.task_service.list_by_project(ctx.project.id)
    )
    return (
        "\n".join(f"{t.id} | [{t.status}] {t.title} | assigned={t.assigned_agent_id}" for t in tasks)
        or "No tasks."
    )


async def _run_get_task_details(ctx: RunContext, tool_input: dict) -> str:
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


async def _run_execute_command(ctx: RunContext, tool_input: dict) -> str:
    command = str(tool_input["command"])
    timeout = int(tool_input.get("timeout", 120))
    svc = E2BService()
    metadata = await svc.ensure_running_sandbox(
        ctx.db,
        ctx.agent,
        persistent=bool(ctx.agent.sandbox_persist),
    )
    await ctx.db.flush()

    if is_local_fallback_sandbox(metadata.sandbox_id):
        return LOCAL_FALLBACK_SANDBOX_ERROR
    if AsyncSandbox is None:
        return "E2B SDK not available in this environment."

    os.environ["E2B_API_KEY"] = settings.e2b_api_key
    sandbox = await AsyncSandbox.connect(metadata.sandbox_id, timeout=settings.e2b_timeout_seconds)
    proc = await sandbox.process.start(command, timeout=timeout)
    await proc.wait()
    parts: list[str] = []
    if metadata.restarted:
        parts.append(metadata.message or f"Sandbox restarted: {metadata.sandbox_id}")
    elif metadata.created:
        parts.append(metadata.message or f"Sandbox created: {metadata.sandbox_id}")
    else:
        parts.append(f"Sandbox ready: {metadata.sandbox_id}")
    parts.append(f"Exit Code: {proc.exit_code}")
    if proc.stdout:
        parts.append(f"Stdout:\n{proc.stdout}")
    if proc.stderr:
        parts.append(f"Stderr:\n{proc.stderr}")
    return "\n".join(parts).strip()


async def _run_start_sandbox(ctx: RunContext, tool_input: dict) -> str:
    svc = E2BService()
    metadata = await svc.ensure_running_sandbox(
        ctx.db,
        ctx.agent,
        persistent=bool(ctx.agent.sandbox_persist),
    )
    await ctx.db.flush()

    if is_local_fallback_sandbox(metadata.sandbox_id):
        return (
            f"Sandbox ready (local fallback): {metadata.sandbox_id}. "
            "Remote E2B execution is unavailable in this environment."
        )
    if metadata.restarted:
        return metadata.message or f"Sandbox restarted: {metadata.sandbox_id}"
    if metadata.created:
        return metadata.message or f"Sandbox created: {metadata.sandbox_id}"
    return metadata.message or f"Sandbox already running: {metadata.sandbox_id}"


async def _run_list_branches(ctx: RunContext, tool_input: dict) -> str:
    repo_path = settings.code_repo_path
    try:
        subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--is-inside-work-tree"],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.output or "").strip()
        raise RuntimeError(detail or f"Git repository not initialized at {repo_path}.") from exc
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_path, "branch", "--list"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise RuntimeError(detail or f"Failed to list branches in repository: {repo_path}") from exc
    return output.strip() or "No branches."


async def _run_view_diff(ctx: RunContext, tool_input: dict) -> str:
    base = str(tool_input.get("base", "main"))
    head = str(tool_input.get("head", "HEAD"))
    output = subprocess.check_output(
        ["git", "-C", settings.code_repo_path, "diff", f"{base}...{head}"],
        text=True,
    )
    return output.strip() or "No diff."


async def _run_create_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise RuntimeError("Only manager can create tasks")
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


async def _run_assign_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise RuntimeError("Only manager can assign tasks")
    task = await ctx.task_service.assign(
        parse_tool_uuid(tool_input, "task_id"),
        parse_tool_uuid(tool_input, "agent_id"),
    )
    await ctx.db.flush()
    return f"Task assigned: {task.id} -> {task.assigned_agent_id}"


async def _run_update_task_status(ctx: RunContext, tool_input: dict) -> str:
    task = await ctx.task_service.get(parse_tool_uuid(tool_input, "task_id"))
    if ctx.agent.role == "engineer" and task.assigned_agent_id != ctx.agent.id:
        raise RuntimeError("Engineers can only update their own tasks")
    task = await ctx.task_service.update_status(task.id, str(tool_input["status"]))
    await ctx.db.flush()
    return f"Task status updated: {task.id} -> {task.status}"


async def _run_abort_task(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "engineer":
        raise RuntimeError("Only engineers can abort tasks")
    if ctx.agent.current_task_id is None:
        raise RuntimeError("No active task to abort")
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


async def _run_interrupt_agent(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"manager", "cto"}:
        raise RuntimeError("Only manager/cto can interrupt")
    from backend.workers.worker_manager import get_worker_manager

    target_id = parse_tool_uuid(tool_input, "target_agent_id")
    get_worker_manager().interrupt_agent(target_id)
    return f"Interrupted agent {target_id}"


async def _run_spawn_engineer(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"manager", "cto"}:
        raise RuntimeError("Only manager/cto can spawn engineers")
    engineer = await ctx.agent_service.spawn_engineer(
        ctx.project.id,
        display_name=str(tool_input["display_name"]),
        seniority=str(tool_input["seniority"]) if tool_input.get("seniority") else None,
    )
    await ctx.db.flush()
    from backend.workers.worker_manager import get_worker_manager
    from backend.workers.message_router import get_message_router

    await get_worker_manager().spawn_worker(engineer.id, engineer.project_id)
    get_message_router().notify(engineer.id)
    return (
        f"Engineer spawned: {engineer.id}\n"
        f"The engineer is now awake. Send it a message or assign a task to give it work."
    )


async def _run_list_agents(ctx: RunContext, tool_input: dict) -> str:
    res = await ctx.db.execute(select(Agent).where(Agent.project_id == ctx.project.id))
    rows = list(res.scalars().all())
    return "\n".join(f"{a.id} | {a.display_name} | {a.role} | {a.status}" for a in rows)


async def _run_create_branch(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"cto", "engineer"}:
        raise RuntimeError("Only cto/engineer can create branches")
    repo_path = settings.code_repo_path
    subprocess.check_output(["git", "-C", repo_path, "checkout", "main"], text=True)
    subprocess.check_output(
        ["git", "-C", repo_path, "checkout", "-b", str(tool_input["branch_name"])],
        text=True,
    )
    return f"Branch created: {tool_input['branch_name']}"


async def _run_create_pull_request(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role not in {"cto", "engineer"}:
        raise RuntimeError("Only cto/engineer can create PRs")
    from backend.services.git_service import GitService

    current_branch = subprocess.check_output(
        ["git", "-C", settings.code_repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
    ).strip()
    svc = GitService(settings.code_repo_path)
    pr = svc.create_pr(ctx.agent.role, current_branch, "main")
    return f"PR created: {pr.pr_url}"


# ---------------------------------------------------------------------------
# Tool registry — built from tool_descriptions.json + executor map
#
# Adding a new tool:
#   1. Add the entry to tool_descriptions.json (name, description, schema, roles)
#   2. Write the executor function above
#   3. Map name → executor in _TOOL_EXECUTORS below
# ---------------------------------------------------------------------------


def _role_has_tool(tool: LoopTool, role: str) -> bool:
    return "*" in tool.allowed_roles or role in tool.allowed_roles


async def _run_describe_tool(ctx: RunContext, tool_input: dict) -> str:
    tool_name = tool_input.get("tool_name")
    if not tool_name:
        available = [t for t in _TOOLS if _role_has_tool(t, ctx.agent.role)]
        lines = ["Available tools:\n"]
        for t in available:
            lines.append(f"  - {t.name}: {t.description}")
        lines.append("\nCall describe_tool(tool_name) for detailed usage information.")
        return "\n".join(lines)

    tool = next((t for t in _TOOLS if t.name == tool_name), None)
    if tool is None:
        return f"Unknown tool: '{tool_name}'. Call describe_tool() with no arguments to see available tools."
    if not _role_has_tool(tool, ctx.agent.role):
        return f"Tool '{tool_name}' exists but is not available to your role ({ctx.agent.role})."

    detail = _TOOL_DETAILS.get(tool_name, "No detailed description available.")
    props = tool.input_schema.get("properties", {})
    required = tool.input_schema.get("required", [])

    lines = [f"## {tool_name}\n", detail, ""]
    if props:
        lines.append("Parameters:")
        for pname, pschema in props.items():
            req_label = "required" if pname in required else "optional"
            ptype = pschema.get("type", "any")
            pdesc = pschema.get("description", "")
            suffix = f" — {pdesc}" if pdesc else ""
            lines.append(f"  - {pname} ({ptype}, {req_label}){suffix}")
    else:
        lines.append("Parameters: none")

    roles = tool.allowed_roles
    role_text = "all roles" if "*" in roles else ", ".join(roles)
    lines.append(f"\nAvailable to: {role_text}")
    return "\n".join(lines)


_TOOL_EXECUTORS: dict[str, ToolExecutor | None] = {
    "end": None,
    "notify_user": _run_notify_user,
    "broadcast_message": _run_broadcast_message,
    "update_memory": _run_update_memory,
    "read_history": _run_read_history,
    "sleep": _run_sleep,
    "list_tasks": _run_list_tasks,
    "get_task_details": _run_get_task_details,
    "execute_command": _run_execute_command,
    "start_sandbox": _run_start_sandbox,
    "list_branches": _run_list_branches,
    "view_diff": _run_view_diff,
    "create_task": _run_create_task,
    "assign_task": _run_assign_task,
    "update_task_status": _run_update_task_status,
    "abort_task": _run_abort_task,
    "interrupt_agent": _run_interrupt_agent,
    "spawn_engineer": _run_spawn_engineer,
    "list_agents": _run_list_agents,
    "describe_tool": _run_describe_tool,
    "create_branch": _run_create_branch,
    "create_pull_request": _run_create_pull_request,
}

_RAW_TOOLS: list[dict] = json.loads(
    (Path(__file__).parent / "tool_descriptions.json").read_text(encoding="utf-8")
)

_TOOLS: list[LoopTool] = [
    LoopTool(
        name=t["name"],
        description=t["description"],
        input_schema=t["input_schema"],
        allowed_roles=t["allowed_roles"],
        execute=_TOOL_EXECUTORS.get(t["name"]),
    )
    for t in _RAW_TOOLS
]

def _normalize_detailed_description(raw: str | list[str]) -> str:
    """Join list of lines into one string; leave string as-is (e.g. from older JSON)."""
    if isinstance(raw, list):
        return "\n".join(raw)
    return raw


_TOOL_DETAILS: dict[str, str] = {
    t["name"]: _normalize_detailed_description(t["detailed_description"])
    for t in _RAW_TOOLS
}


# ---------------------------------------------------------------------------
# Public API for loop.py
# ---------------------------------------------------------------------------


def get_tool_defs_for_role(role: str) -> list[dict]:
    """Return the LLM tool-definition list for the given agent role."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in _TOOLS
        if _role_has_tool(t, role)
    ]


def get_handlers_for_role(role: str) -> dict[str, ToolExecutor]:
    """Return a name→executor map for all dispatchable tools for the given role.

    'end' is excluded because the loop handles it separately before dispatch.
    """
    return {
        t.name: t.execute
        for t in _TOOLS
        if t.name != "end" and t.execute is not None and _role_has_tool(t, role)
    }
