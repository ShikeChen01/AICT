"""Tool registry for the universal agent loop.

Builds the _TOOLS list from tool_descriptions.json and maps each tool name to
its executor function. All executor implementations live in backend/tools/executors/.

Adding a new tool:
  1. Add the entry to tool_descriptions.json (name, description, schema, roles).
  2. Write the executor in the appropriate executors/ module.
  3. Map name -> executor in _TOOL_EXECUTORS below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from backend.tools.base import (
    LoopTool,
    RunContext,
    ToolExecutor,
    truncate_tool_output,
    parse_tool_uuid,
)
from backend.tools.executors.messaging import run_send_message, run_broadcast_message
from backend.tools.executors.memory import run_compact_history, run_update_memory, run_read_history, run_list_sessions
from backend.tools.executors.tasks import (
    run_list_tasks,
    run_get_task_details,
    run_create_task,
    run_assign_task,
    run_update_task_status,
    run_abort_task,
)
from backend.tools.executors.sandbox import (
    _get_sandbox_service,
    run_execute_command,
    run_sandbox_start_session,
    run_sandbox_end_session,
    run_sandbox_health,
    run_sandbox_screenshot,
    run_sandbox_mouse_move,
    run_sandbox_mouse_click,
    run_sandbox_mouse_scroll,
    run_sandbox_mouse_location,
    run_sandbox_keyboard_press,
    run_sandbox_record_screen,
    run_sandbox_end_record_screen,
)
from backend.tools.executors.agents import (
    run_spawn_engineer,
    run_list_agents,
    run_remove_agent,
    run_interrupt_agent,
)
from backend.tools.executors.meta import run_sleep, run_get_project_metadata
from backend.tools.executors.docs import run_write_architecture_doc

# Re-export for backward-compat with loop.py imports
__all__ = [
    "RunContext",
    "LoopTool",
    "ToolExecutor",
    "truncate_tool_output",
    "parse_tool_uuid",
    "get_tool_defs_for_role",
    "get_tool_defs_for_agent",
    "get_handlers_for_role",
    "get_thinking_phase_tool_defs",
    "get_thinking_phase_handlers",
    "validate_tool_input",
]

# Underscore-prefixed aliases for test backward-compatibility
_run_execute_command = run_execute_command
_run_spawn_engineer = run_spawn_engineer
_run_sandbox_start_session = run_sandbox_start_session
_run_start_sandbox = run_sandbox_start_session
_run_sandbox_end_session = run_sandbox_end_session
_run_sandbox_health = run_sandbox_health
_run_sandbox_screenshot = run_sandbox_screenshot
_run_sandbox_mouse_move = run_sandbox_mouse_move
_run_sandbox_mouse_click = run_sandbox_mouse_click
_run_sandbox_mouse_scroll = run_sandbox_mouse_scroll
_run_sandbox_mouse_location = run_sandbox_mouse_location
_run_sandbox_keyboard_press = run_sandbox_keyboard_press
_run_sandbox_record_screen = run_sandbox_record_screen
_run_sandbox_end_record_screen = run_sandbox_end_record_screen


# ---------------------------------------------------------------------------
# Tool executor map
# ---------------------------------------------------------------------------

_TOOL_EXECUTORS: dict[str, ToolExecutor | None] = {
    "end": None,
    "send_message": run_send_message,
    "broadcast_message": run_broadcast_message,
    "compact_history": run_compact_history,
    "update_memory": run_update_memory,
    "read_history": run_read_history,
    "list_sessions": run_list_sessions,
    "sleep": run_sleep,
    "list_tasks": run_list_tasks,
    "get_task_details": run_get_task_details,
    "execute_command": run_execute_command,
    "sandbox_start_session": run_sandbox_start_session,
    "sandbox_end_session": run_sandbox_end_session,
    "sandbox_health": run_sandbox_health,
    "sandbox_screenshot": run_sandbox_screenshot,
    "sandbox_mouse_move": run_sandbox_mouse_move,
    "sandbox_mouse_click": run_sandbox_mouse_click,
    "sandbox_mouse_scroll": run_sandbox_mouse_scroll,
    "sandbox_mouse_location": run_sandbox_mouse_location,
    "sandbox_keyboard_press": run_sandbox_keyboard_press,
    "sandbox_record_screen": run_sandbox_record_screen,
    "sandbox_end_record_screen": run_sandbox_end_record_screen,
    "create_task": run_create_task,
    "assign_task": run_assign_task,
    "update_task_status": run_update_task_status,
    "abort_task": run_abort_task,
    "interrupt_agent": run_interrupt_agent,
    "spawn_engineer": run_spawn_engineer,
    "list_agents": run_list_agents,
    "remove_agent": run_remove_agent,
    "describe_tool": None,  # assigned below after _TOOLS is built
    "get_project_metadata": run_get_project_metadata,
    "write_architecture_doc": run_write_architecture_doc,
    "thinking_done": None,  # stage-transition tool — handled directly by loop.py, not dispatched
}


# ---------------------------------------------------------------------------
# Build _TOOLS from tool_descriptions.json
# ---------------------------------------------------------------------------

_RAW_TOOLS: list[dict] = json.loads(
    (Path(__file__).parent / "tool_descriptions.json").read_text(encoding="utf-8")
)


def _normalize_detailed_description(raw: str | list[str]) -> str:
    if isinstance(raw, list):
        return "\n".join(raw)
    return raw


_TOOL_DETAILS: dict[str, str] = {
    t["name"]: _normalize_detailed_description(t["detailed_description"])
    for t in _RAW_TOOLS
}

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


# ---------------------------------------------------------------------------
# describe_tool — defined here because it needs access to _TOOLS/_TOOL_DETAILS
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


# Patch describe_tool executor now that _TOOLS is built
for _t in _TOOLS:
    if _t.name == "describe_tool":
        _t.execute = _run_describe_tool
_TOOL_EXECUTORS["describe_tool"] = _run_describe_tool


# ---------------------------------------------------------------------------
# Public API consumed by loop.py
# ---------------------------------------------------------------------------


def get_tool_defs_for_role(role: str) -> list[dict]:
    """Return the LLM tool-definition list for the given agent role (from static JSON).

    Used during thinking phase and as fallback. For the main agent loop,
    prefer get_tool_defs_for_agent() which reads from DB (user-customized).
    """
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in _TOOLS
        if _role_has_tool(t, role)
    ]


async def get_tool_defs_for_agent(agent_id, role: str, db) -> list[dict]:
    """Return LLM tool-definition list for an agent, reading from DB (user-customized).

    Falls back to static JSON definitions for any tool not found in DB.
    Only enabled tools are returned. Ordered by position.
    """
    from uuid import UUID
    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(db)
    role_map = {"manager": "manager", "cto": "cto", "engineer": "worker"}
    base_role = role_map.get(role, "worker")
    db_tools = await repo.ensure_agent_tools(agent_id, base_role)

    result = []
    for tc in db_tools:
        if not tc.enabled:
            continue
        result.append({
            "name": tc.tool_name,
            "description": tc.description,
            "input_schema": tc.input_schema or {},
        })
    return result


def validate_tool_input(tool_name: str, tool_input: dict) -> None:
    """Check tool_input against the tool's input_schema.

    Raises ValueError with an actionable message listing every missing required
    parameter so the LLM can self-correct.
    """
    tool = next((t for t in _TOOLS if t.name == tool_name), None)
    if tool is None:
        return
    required = tool.input_schema.get("required", [])
    if not required:
        return
    properties = tool.input_schema.get("properties", {})
    missing = [r for r in required if r not in tool_input]
    if missing:
        details = ", ".join(
            f"'{m}' ({properties.get(m, {}).get('type', 'any')})" for m in missing
        )
        raise ValueError(f"Missing required parameter(s): {details}")


def get_handlers_for_role(role: str) -> dict[str, ToolExecutor]:
    """Return a name→executor map for all dispatchable tools for the given role.

    'end' and 'thinking_done' are excluded — the loop handles them separately.
    """
    excluded = {"end", "thinking_done"}
    return {
        t.name: t.execute
        for t in _TOOLS
        if t.name not in excluded and t.execute is not None and _role_has_tool(t, role)
    }


# Tools available during the thinking phase (Stage 1)
_THINKING_PHASE_TOOL_NAMES = frozenset({
    "compact_history",
    "update_memory",
    "read_history",
    "list_sessions",
    "thinking_done",
})


def get_thinking_phase_tool_defs(role: str) -> list[dict]:
    """Return tool defs for the thinking phase (restricted tool set).

    Only planning tools + thinking_done are available during Stage 1.
    """
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in _TOOLS
        if t.name in _THINKING_PHASE_TOOL_NAMES and _role_has_tool(t, role)
    ]


def get_thinking_phase_handlers() -> dict[str, ToolExecutor]:
    """Return executor map for thinking phase tools (excluding thinking_done)."""
    return {
        t.name: t.execute
        for t in _TOOLS
        if t.name in _THINKING_PHASE_TOOL_NAMES
        and t.name != "thinking_done"
        and t.execute is not None
    }
