"""Tool executors — sandbox: execute_command and all sandbox_* interaction tools."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError


@dataclass
class ScreenshotResult:
    """Wraps screenshot bytes so the loop can inject them as vision image_parts."""
    image_bytes: bytes
    media_type: str = "image/jpeg"


def _get_sandbox_service():
    from backend.services.sandbox_service import SandboxService
    return SandboxService()


async def run_execute_command(ctx: RunContext, tool_input: dict) -> str:
    command = str(tool_input["command"])
    timeout = int(tool_input.get("timeout", 120))
    prev_sandbox_id = ctx.agent.sandbox_id
    svc = _get_sandbox_service()
    result = await svc.execute_command(ctx.db, ctx.agent, command, timeout=timeout)
    # If sandbox was just created (first execute_command), commit and broadcast
    if ctx.agent.sandbox_id != prev_sandbox_id:
        await _commit_and_broadcast_sandbox(ctx)
    parts: list[str] = [f"Sandbox: {ctx.agent.sandbox_id}"]
    if result.truncated:
        parts.append("[output truncated]")
    if result.exit_code is None and not result.stdout.strip():
        parts.append(
            f"[command timed out after {timeout}s — no output received. "
            "The sandbox may still be starting up. Try again in a few seconds.]"
        )
    else:
        parts.append(result.stdout)
    if result.exit_code is not None:
        parts.append(f"Exit Code: {result.exit_code}")
    return "\n".join(parts).strip()


async def _commit_and_broadcast_sandbox(ctx: RunContext) -> None:
    """Commit sandbox_id to DB and broadcast so the frontend sees it immediately."""
    await ctx.db.commit()
    from backend.websocket.manager import ws_manager
    await ws_manager.broadcast_agent_status(ctx.agent)


async def run_sandbox_start_session(ctx: RunContext, tool_input: dict) -> str:
    svc = _get_sandbox_service()
    meta = await svc.ensure_running_sandbox(ctx.db, ctx.agent)
    # Commit immediately so sandbox_id is visible to other DB sessions (API endpoints)
    # and broadcast agent_status so the frontend refreshes and picks up the new sandbox_id.
    await _commit_and_broadcast_sandbox(ctx)
    return meta.message or f"Sandbox ready: {meta.sandbox_id}"


async def run_sandbox_end_session(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox_id:
        return "No active sandbox to end."
    svc = _get_sandbox_service()
    await svc.close_sandbox(ctx.db, ctx.agent)
    await _commit_and_broadcast_sandbox(ctx)
    return "Sandbox session ended. Container returned to pool."


async def run_sandbox_health(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox_id:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Call sandbox_start_session() to allocate a sandbox, then retry.",
        )
    svc = _get_sandbox_service()
    try:
        data = await svc.sandbox_health(ctx.agent)
        return (
            f"status={data.get('status')} "
            f"uptime={data.get('uptime_seconds')}s "
            f"display={data.get('display')}"
        )
    except Exception as exc:
        raise ToolExecutionError(
            f"Health check failed: {type(exc).__name__}: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Try calling sandbox_start_session() to re-allocate the container.",
        ) from exc


async def run_sandbox_screenshot(ctx: RunContext, tool_input: dict) -> str | ScreenshotResult:
    """Capture a screenshot; returns ScreenshotResult so the loop can inject the
    image into the LLM conversation as a vision image_part."""
    if not ctx.agent.sandbox_id:
        await run_sandbox_start_session(ctx, {})
    svc = _get_sandbox_service()
    try:
        img_bytes = await svc.take_screenshot(ctx.agent)
        return ScreenshotResult(image_bytes=img_bytes, media_type="image/jpeg")
    except Exception as exc:
        raise ToolExecutionError(
            f"Screenshot failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Check sandbox_health() and ensure a display application is running.",
        ) from exc


async def run_sandbox_mouse_move(ctx: RunContext, tool_input: dict) -> str:
    x = int(tool_input["x"])
    y = int(tool_input["y"])
    svc = _get_sandbox_service()
    try:
        await svc.mouse_move(ctx.agent, x, y)
        return f"Mouse moved to ({x}, {y})"
    except Exception as exc:
        raise ToolExecutionError(
            f"Mouse move failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_mouse_click(ctx: RunContext, tool_input: dict) -> str:
    x = tool_input.get("x")
    y = tool_input.get("y")
    button = int(tool_input.get("button", 1))
    click_type = tool_input.get("click_type", "single")
    svc = _get_sandbox_service()
    try:
        result = await svc.mouse_click(ctx.agent, x=x, y=y, button=button, click_type=click_type)
        pos = result or {}
        return f"Mouse clicked at ({pos.get('x', x)}, {pos.get('y', y)}) button={button} type={click_type}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Mouse click failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_mouse_scroll(ctx: RunContext, tool_input: dict) -> str:
    x = tool_input.get("x")
    y = tool_input.get("y")
    direction = tool_input.get("direction", "down")
    clicks = int(tool_input.get("clicks", 3))
    svc = _get_sandbox_service()
    try:
        await svc.mouse_scroll(ctx.agent, x=x, y=y, direction=direction, clicks=clicks)
        return f"Scrolled {direction} {clicks} click(s) at ({x}, {y})"
    except Exception as exc:
        raise ToolExecutionError(
            f"Mouse scroll failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_mouse_location(ctx: RunContext, tool_input: dict) -> str:
    svc = _get_sandbox_service()
    try:
        loc = await svc.mouse_location(ctx.agent)
        return f"Mouse at x={loc.get('x')}, y={loc.get('y')}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Mouse location failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_keyboard_press(ctx: RunContext, tool_input: dict) -> str:
    keys = tool_input.get("keys")
    text = tool_input.get("text")
    if not keys and not text:
        raise ToolExecutionError(
            "Provide exactly one of 'keys' or 'text'.",
            error_code=ToolExecutionError.INVALID_INPUT,
            hint="Use 'keys' for special combos (e.g. 'ctrl+c') or 'text' to type characters.",
        )
    svc = _get_sandbox_service()
    try:
        await svc.keyboard_press(ctx.agent, keys=keys, text=text)
        return f"Keyboard input sent: keys={keys!r} text={text!r}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Keyboard press failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_record_screen(ctx: RunContext, tool_input: dict) -> str:
    svc = _get_sandbox_service()
    try:
        data = await svc.start_recording(ctx.agent)
        return f"Recording started. Status: {data.get('status')}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Start recording failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_end_record_screen(ctx: RunContext, tool_input: dict) -> str:
    svc = _get_sandbox_service()
    try:
        video_bytes = await svc.stop_recording(ctx.agent)
        b64 = base64.b64encode(video_bytes).decode()
        return f"Recording stopped ({len(video_bytes)} bytes). Base64 MP4:\n{b64[:200]}...[truncated for display]"
    except Exception as exc:
        raise ToolExecutionError(
            f"Stop recording failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc
