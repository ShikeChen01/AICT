"""Tool executors — desktop: GUI interaction and convenience tools for desktop VMs."""

from __future__ import annotations

from backend.logging.my_logger import get_logger
from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError
from backend.tools.executors.sandbox import ScreenshotResult

logger = get_logger(__name__)


def _get_sandbox_service():
    from backend.services.sandbox_service import SandboxService
    return SandboxService()


def _require_desktop(ctx: RunContext) -> "Sandbox":
    desktop = ctx.agent.desktop
    if not desktop:
        raise ToolExecutionError(
            "No desktop assigned — ask the user to assign a desktop to this agent.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    return desktop


# ---------------------------------------------------------------------------
# 5 GUI tools (mirror sandbox_* pattern)
# ---------------------------------------------------------------------------


async def run_desktop_screenshot(ctx: RunContext, tool_input: dict) -> str | ScreenshotResult:
    """Capture a screenshot of the desktop VM display; returns ScreenshotResult
    so the loop can inject the image into the LLM conversation as a vision image_part."""
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        img_bytes = await svc.take_screenshot(desktop)
        return ScreenshotResult(image_bytes=img_bytes, media_type="image/jpeg")
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop screenshot failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Check that the desktop VM is running and the display is active.",
        ) from exc


async def run_desktop_mouse_move(ctx: RunContext, tool_input: dict) -> str:
    """Move mouse cursor to (x, y) on the desktop VM display."""
    x = int(tool_input["x"])
    y = int(tool_input["y"])
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        await svc.mouse_move(desktop, x, y)
        return f"Mouse moved to ({x}, {y})"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop mouse move failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_mouse_click(ctx: RunContext, tool_input: dict) -> str:
    """Click the mouse at optional (x, y) coordinates on the desktop VM display."""
    x = tool_input.get("x")
    y = tool_input.get("y")
    button = int(tool_input.get("button", 1))
    click_type = tool_input.get("click_type", "single")
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        result = await svc.mouse_click(desktop, x=x, y=y, button=button, click_type=click_type)
        pos = result or {}
        return f"Mouse clicked at ({pos.get('x', x)}, {pos.get('y', y)}) button={button} type={click_type}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop mouse click failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_mouse_scroll(ctx: RunContext, tool_input: dict) -> str:
    """Scroll the mouse wheel at optional (x, y) coordinates on the desktop VM display."""
    x = tool_input.get("x")
    y = tool_input.get("y")
    direction = tool_input.get("direction", "down")
    clicks = int(tool_input.get("clicks", 3))
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        await svc.mouse_scroll(desktop, x=x, y=y, direction=direction, clicks=clicks)
        return f"Scrolled {direction} {clicks} click(s) at ({x}, {y})"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop mouse scroll failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_keyboard_press(ctx: RunContext, tool_input: dict) -> str:
    """Send key press or type text on the desktop VM display."""
    keys = tool_input.get("keys")
    text = tool_input.get("text")
    if not keys and not text:
        raise ToolExecutionError(
            "Provide exactly one of 'keys' or 'text'.",
            error_code=ToolExecutionError.INVALID_INPUT,
            hint="Use 'keys' for special combos (e.g. 'ctrl+c') or 'text' to type characters.",
        )
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        await svc.keyboard_press(desktop, keys=keys, text=text)
        return f"Keyboard input sent: keys={keys!r} text={text!r}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop keyboard press failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


# ---------------------------------------------------------------------------
# 5 Convenience tools
# ---------------------------------------------------------------------------


async def run_desktop_open_url(ctx: RunContext, tool_input: dict) -> str:
    """Open a URL in Google Chrome on the desktop VM."""
    url = str(tool_input["url"])
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        cmd = f'DISPLAY=:99 google-chrome --no-first-run --disable-session-crashed-bubble --disable-infobars "{url}" &'
        result = await svc.execute_command(desktop, cmd, timeout=15)
        parts = [f"Opening URL: {url}"]
        if result.stdout.strip():
            parts.append(result.stdout)
        return "\n".join(parts).strip()
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop open_url failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
            hint="Ensure Google Chrome is installed on the desktop VM.",
        ) from exc


async def run_desktop_list_windows(ctx: RunContext, tool_input: dict) -> str:
    """List open windows on the desktop VM display."""
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        result = await svc.execute_command(desktop, "DISPLAY=:99 wmctrl -l -p", timeout=10)
        if result.exit_code == 0 and result.stdout.strip():
            return result.stdout.strip()
        # wmctrl fallback: try xdotool
        fallback = await svc.execute_command(
            desktop,
            "DISPLAY=:99 xdotool search --onlyvisible --name '' getwindowname %@",
            timeout=10,
        )
        if fallback.stdout.strip():
            return fallback.stdout.strip()
        return "No windows found (or wmctrl/xdotool not available)."
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop list_windows failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_focus_window(ctx: RunContext, tool_input: dict) -> str:
    """Focus a window on the desktop VM by title or window ID."""
    title = tool_input.get("title")
    window_id = tool_input.get("window_id")
    if not title and not window_id:
        raise ToolExecutionError(
            "Provide at least one of 'title' or 'window_id'.",
            error_code=ToolExecutionError.INVALID_INPUT,
            hint="Use desktop_list_windows to discover available windows.",
        )
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        if window_id:
            # Try wmctrl first, fall back to xdotool
            result = await svc.execute_command(
                desktop, f"DISPLAY=:99 wmctrl -i -a {window_id}", timeout=10
            )
            if result.exit_code != 0:
                result = await svc.execute_command(
                    desktop, f"DISPLAY=:99 xdotool windowactivate {window_id}", timeout=10
                )
            return f"Focused window ID: {window_id}"
        else:
            # Focus by title
            result = await svc.execute_command(
                desktop, f"DISPLAY=:99 wmctrl -a '{title}'", timeout=10
            )
            if result.exit_code != 0:
                result = await svc.execute_command(
                    desktop,
                    f"DISPLAY=:99 xdotool search --name '{title}' windowactivate",
                    timeout=10,
                )
            return f"Focused window: {title}"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop focus_window failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_get_clipboard(ctx: RunContext, tool_input: dict) -> str:
    """Get the clipboard contents from the desktop VM."""
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        result = await svc.execute_command(
            desktop,
            "DISPLAY=:99 xclip -selection clipboard -o 2>/dev/null || xsel --clipboard --output 2>/dev/null",
            timeout=10,
        )
        if result.stdout.strip():
            return result.stdout.strip()
        return "(clipboard is empty)"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop get_clipboard failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc


async def run_desktop_set_clipboard(ctx: RunContext, tool_input: dict) -> str:
    """Set the clipboard contents on the desktop VM."""
    content = str(tool_input["content"])
    desktop = _require_desktop(ctx)
    svc = _get_sandbox_service()
    try:
        # Pipe content to xclip via printf to handle special characters safely
        escaped = content.replace("\\", "\\\\").replace("'", "'\\''")
        cmd = f"printf '%s' '{escaped}' | DISPLAY=:99 xclip -selection clipboard"
        result = await svc.execute_command(desktop, cmd, timeout=10)
        return f"Clipboard set ({len(content)} chars)"
    except Exception as exc:
        raise ToolExecutionError(
            f"Desktop set_clipboard failed: {exc}",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        ) from exc
