"""
Unit tests for desktop tool executors.

Tests the 10 desktop_* tools defined in backend/tools/executors/desktop.py.
All tests mock the SandboxService — no real network or VM interaction.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_client import ShellResult
from backend.tools.executors.desktop import (
    _require_desktop,
    run_desktop_screenshot,
    run_desktop_mouse_move,
    run_desktop_mouse_click,
    run_desktop_mouse_scroll,
    run_desktop_keyboard_press,
    run_desktop_open_url,
    run_desktop_list_windows,
    run_desktop_focus_window,
    run_desktop_get_clipboard,
    run_desktop_set_clipboard,
)
from backend.tools.executors.sandbox import ScreenshotResult
from backend.tools.result import ToolExecutionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_desktop():
    """Create a mock desktop Sandbox object (unit_type='desktop')."""
    sb = MagicMock()
    sb.id = uuid.uuid4()
    sb.host = "10.0.0.1"
    sb.port = 30001
    sb.auth_token = "tok-desktop"
    sb.orchestrator_sandbox_id = "orch-desktop-001"
    sb.unit_type = "desktop"
    return sb


def _make_ctx(*, has_desktop: bool = True, has_sandbox: bool = False):
    """Create a mock RunContext."""
    ctx = MagicMock()
    ctx.agent.desktop = _make_desktop() if has_desktop else None
    ctx.agent.sandbox = MagicMock() if has_sandbox else None
    return ctx


def _mock_svc():
    """Create a mock SandboxService."""
    svc = MagicMock()
    svc.take_screenshot = AsyncMock(return_value=b"JPEG_BYTES")
    svc.mouse_move = AsyncMock(return_value={"ok": True, "x": 10, "y": 20})
    svc.mouse_click = AsyncMock(return_value={"ok": True, "x": 100, "y": 200})
    svc.mouse_scroll = AsyncMock(return_value={"ok": True})
    svc.keyboard_press = AsyncMock(return_value={"ok": True})
    svc.execute_command = AsyncMock(return_value=ShellResult(stdout="output", exit_code=0))
    return svc


# ---------------------------------------------------------------------------
# _require_desktop guard
# ---------------------------------------------------------------------------


def test_require_desktop_returns_desktop():
    ctx = _make_ctx(has_desktop=True)
    result = _require_desktop(ctx)
    assert result is ctx.agent.desktop
    assert result.unit_type == "desktop"


def test_require_desktop_raises_when_no_desktop():
    ctx = _make_ctx(has_desktop=False)
    with pytest.raises(ToolExecutionError, match="No desktop assigned"):
        _require_desktop(ctx)


def test_require_desktop_ignores_sandbox():
    """_require_desktop checks agent.desktop, not agent.sandbox."""
    ctx = _make_ctx(has_desktop=False, has_sandbox=True)
    with pytest.raises(ToolExecutionError, match="No desktop assigned"):
        _require_desktop(ctx)


# ---------------------------------------------------------------------------
# GUI tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_desktop_screenshot_returns_screenshot_result():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_screenshot(ctx, {})
    assert isinstance(result, ScreenshotResult)
    assert result.image_bytes == b"JPEG_BYTES"
    svc.take_screenshot.assert_awaited_once_with(ctx.agent.desktop)


@pytest.mark.asyncio
async def test_desktop_screenshot_raises_without_desktop():
    ctx = _make_ctx(has_desktop=False)
    with pytest.raises(ToolExecutionError, match="No desktop assigned"):
        await run_desktop_screenshot(ctx, {})


@pytest.mark.asyncio
async def test_desktop_mouse_move():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_mouse_move(ctx, {"x": 100, "y": 200})
    assert "100" in result and "200" in result
    svc.mouse_move.assert_awaited_once_with(ctx.agent.desktop, 100, 200)


@pytest.mark.asyncio
async def test_desktop_mouse_click():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_mouse_click(ctx, {"x": 50, "y": 75, "button": 1, "click_type": "double"})
    assert "double" in result
    svc.mouse_click.assert_awaited_once_with(ctx.agent.desktop, x=50, y=75, button=1, click_type="double")


@pytest.mark.asyncio
async def test_desktop_mouse_scroll():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_mouse_scroll(ctx, {"direction": "up", "clicks": 5})
    assert "up" in result and "5" in result
    svc.mouse_scroll.assert_awaited_once_with(ctx.agent.desktop, x=None, y=None, direction="up", clicks=5)


@pytest.mark.asyncio
async def test_desktop_keyboard_press_keys():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_keyboard_press(ctx, {"keys": "ctrl+c"})
    assert "ctrl+c" in result
    svc.keyboard_press.assert_awaited_once_with(ctx.agent.desktop, keys="ctrl+c", text=None)


@pytest.mark.asyncio
async def test_desktop_keyboard_press_text():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_keyboard_press(ctx, {"text": "hello"})
    assert "hello" in result
    svc.keyboard_press.assert_awaited_once_with(ctx.agent.desktop, keys=None, text="hello")


@pytest.mark.asyncio
async def test_desktop_keyboard_press_rejects_empty():
    ctx = _make_ctx()
    with pytest.raises(ToolExecutionError, match="keys.*text"):
        await run_desktop_keyboard_press(ctx, {})


# ---------------------------------------------------------------------------
# Convenience tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_desktop_open_url():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_open_url(ctx, {"url": "https://example.com"})
    assert "https://example.com" in result
    cmd = svc.execute_command.call_args[0][1]
    assert "google-chrome" in cmd
    assert "https://example.com" in cmd


@pytest.mark.asyncio
async def test_desktop_list_windows():
    ctx = _make_ctx()
    svc = _mock_svc()
    svc.execute_command = AsyncMock(
        return_value=ShellResult(stdout="0x01 Desktop\n0x02 Chrome", exit_code=0)
    )
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_list_windows(ctx, {})
    assert "Chrome" in result
    assert "Desktop" in result


@pytest.mark.asyncio
async def test_desktop_focus_window_by_title():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_focus_window(ctx, {"title": "Chrome"})
    assert "Chrome" in result
    cmd = svc.execute_command.call_args_list[0][0][1]
    assert "wmctrl" in cmd
    assert "Chrome" in cmd


@pytest.mark.asyncio
async def test_desktop_focus_window_by_id():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_focus_window(ctx, {"window_id": "0x12345"})
    assert "0x12345" in result


@pytest.mark.asyncio
async def test_desktop_focus_window_rejects_empty():
    ctx = _make_ctx()
    with pytest.raises(ToolExecutionError, match="title.*window_id"):
        await run_desktop_focus_window(ctx, {})


@pytest.mark.asyncio
async def test_desktop_get_clipboard():
    ctx = _make_ctx()
    svc = _mock_svc()
    svc.execute_command = AsyncMock(
        return_value=ShellResult(stdout="clipboard content here", exit_code=0)
    )
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_get_clipboard(ctx, {})
    assert result == "clipboard content here"


@pytest.mark.asyncio
async def test_desktop_get_clipboard_empty():
    ctx = _make_ctx()
    svc = _mock_svc()
    svc.execute_command = AsyncMock(
        return_value=ShellResult(stdout="", exit_code=0)
    )
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_get_clipboard(ctx, {})
    assert "empty" in result


@pytest.mark.asyncio
async def test_desktop_set_clipboard():
    ctx = _make_ctx()
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        result = await run_desktop_set_clipboard(ctx, {"content": "hello world"})
    assert "11 chars" in result
    cmd = svc.execute_command.call_args[0][1]
    assert "xclip" in cmd


# ---------------------------------------------------------------------------
# Isolation: desktop tools don't touch sandbox, sandbox tools don't touch desktop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_desktop_tools_use_desktop_not_sandbox():
    """Desktop tools should pass the desktop object to service methods, never the sandbox."""
    ctx = _make_ctx(has_desktop=True, has_sandbox=True)
    svc = _mock_svc()
    with patch("backend.tools.executors.desktop._get_sandbox_service", return_value=svc):
        await run_desktop_screenshot(ctx, {})
    svc.take_screenshot.assert_awaited_once_with(ctx.agent.desktop)


# ---------------------------------------------------------------------------
# Registry: desktop tools are registered
# ---------------------------------------------------------------------------


def test_desktop_tools_in_registry():
    from backend.tools.loop_registry import _TOOL_EXECUTORS, _DESKTOP_TOOL_NAMES
    for name in _DESKTOP_TOOL_NAMES:
        assert name in _TOOL_EXECUTORS, f"'{name}' not in _TOOL_EXECUTORS"
        assert _TOOL_EXECUTORS[name] is not None, f"'{name}' executor is None"


def test_desktop_tool_names_complete():
    from backend.tools.loop_registry import _DESKTOP_TOOL_NAMES
    expected = {
        "desktop_screenshot",
        "desktop_mouse_move",
        "desktop_mouse_click",
        "desktop_mouse_scroll",
        "desktop_keyboard_press",
        "desktop_open_url",
        "desktop_list_windows",
        "desktop_focus_window",
        "desktop_get_clipboard",
        "desktop_set_clipboard",
    }
    assert _DESKTOP_TOOL_NAMES == expected
