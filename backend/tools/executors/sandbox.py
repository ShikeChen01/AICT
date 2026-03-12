"""Tool executors — sandbox: execute_command and all sandbox_* interaction tools."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from backend.logging.my_logger import get_logger
from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError

logger = get_logger(__name__)


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
    prev_sandbox = ctx.agent.sandbox
    svc = _get_sandbox_service()
    result = await svc.execute_command_legacy(ctx.db, ctx.agent, command, timeout=timeout)
    # If sandbox was just created (first execute_command), commit and broadcast
    if ctx.agent.sandbox != prev_sandbox and ctx.agent.sandbox is not None:
        await _flush_and_broadcast_sandbox(ctx)

    sandbox_id = ctx.agent.sandbox.id if ctx.agent.sandbox else "unknown"
    parts: list[str] = [f"Sandbox: {sandbox_id}"]
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


async def _flush_and_broadcast_sandbox(ctx: RunContext) -> None:
    """Flush sandbox_id to DB and broadcast so the frontend sees it immediately.

    Uses flush() (not commit()) to stay consistent with the transaction pattern
    used by sandbox_service.py — the caller / agent loop owns the final commit.
    The WebSocket broadcast is best-effort: failures are logged but never
    propagated so that sandbox operations are not reported as failed when
    the only issue is a missing WS connection.
    """
    await ctx.db.flush()
    try:
        from backend.websocket.manager import ws_manager
        await ws_manager.broadcast_agent_status(ctx.agent)
    except Exception:
        logger.warning(
            "Failed to broadcast sandbox status for agent %s — will be synced on next poll",
            ctx.agent.id,
            exc_info=True,
        )


async def run_sandbox_start_session(ctx: RunContext, tool_input: dict) -> str:
    svc = _get_sandbox_service()
    meta = await svc.ensure_running_sandbox(ctx.db, ctx.agent)
    # Commit immediately so sandbox relationship is visible to other DB sessions (API endpoints)
    # and broadcast agent_status so the frontend refreshes and picks up the new sandbox.
    await _flush_and_broadcast_sandbox(ctx)
    return meta.message or f"Sandbox ready: {meta.sandbox_id}"


async def run_sandbox_end_session(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox:
        return "No active sandbox to end."
    svc = _get_sandbox_service()
    await svc.close_sandbox(ctx.db, ctx.agent)
    await _flush_and_broadcast_sandbox(ctx)
    return "Sandbox session ended. Container returned to pool."


async def run_sandbox_health(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Call sandbox_start_session() to allocate a sandbox, then retry.",
        )
    svc = _get_sandbox_service()
    try:
        data = await svc.sandbox_health(ctx.agent.sandbox)
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
    if not ctx.agent.sandbox:
        await run_sandbox_start_session(ctx, {})
    svc = _get_sandbox_service()
    try:
        img_bytes = await svc.take_screenshot(ctx.agent.sandbox)
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
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        await svc.mouse_move(ctx.agent.sandbox, x, y)
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
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        result = await svc.mouse_click(ctx.agent.sandbox, x=x, y=y, button=button, click_type=click_type)
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
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        await svc.mouse_scroll(ctx.agent.sandbox, x=x, y=y, direction=direction, clicks=clicks)
        return f"Scrolled {direction} {clicks} click(s) at ({x}, {y})"
    except Exception as exc:
        raise ToolExecutionError(
            f"Mouse scroll failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_mouse_location(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        loc = await svc.mouse_location(ctx.agent.sandbox)
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
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        await svc.keyboard_press(ctx.agent.sandbox, keys=keys, text=text)
        return f"Keyboard input sent: keys={keys!r} text={text!r}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Keyboard press failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_record_screen(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        data = await svc.start_recording(ctx.agent.sandbox)
        return f"Recording started. Status: {data.get('status')}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Start recording failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_sandbox_end_record_screen(ctx: RunContext, tool_input: dict) -> str:
    if not ctx.agent.sandbox:
        raise ToolExecutionError(
            "No active sandbox — call sandbox_start_session first.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    svc = _get_sandbox_service()
    try:
        video_bytes = await svc.stop_recording(ctx.agent.sandbox)
        b64 = base64.b64encode(video_bytes).decode()
        return f"Recording stopped ({len(video_bytes)} bytes). Base64 MP4:\n{b64[:200]}...[truncated for display]"
    except Exception as exc:
        raise ToolExecutionError(
            f"Stop recording failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc
