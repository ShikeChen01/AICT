"""Unit tests for all 22 sandbox and desktop tool executor functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools.result import ToolExecutionError
from backend.tests.sandbox.conftest import make_agent, make_run_context, make_sandbox


# ── Section 1: Guard Functions ───────────────────────────────────────────────


class TestGuardFunctions:
    """Verify that sandbox/desktop tools enforce presence of their compute unit."""

    @pytest.mark.asyncio
    async def test_sandbox_tool_raises_when_no_sandbox(self):
        agent = make_agent(sandbox=None)
        ctx = make_run_context(agent)
        from backend.tools.executors.sandbox import run_execute_command

        with pytest.raises(ToolExecutionError) as exc_info:
            await run_execute_command(ctx, {"command": "ls"})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_sandbox_tool_works_when_sandbox_set(self):
        agent = make_agent(sandbox=make_sandbox())
        ctx = make_run_context(agent)
        mock_svc = AsyncMock()
        from backend.services.sandbox_client import ShellResult

        mock_svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="hello", exit_code=0)
        )
        from backend.tools.executors.sandbox import run_execute_command

        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=mock_svc,
        ):
            result = await run_execute_command(ctx, {"command": "echo hello"})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_desktop_tool_raises_when_no_desktop(self):
        agent = make_agent(desktop=None)
        ctx = make_run_context(agent)
        from backend.tools.executors.desktop import run_desktop_screenshot

        with pytest.raises(ToolExecutionError) as exc_info:
            await run_desktop_screenshot(ctx, {})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_desktop_tool_works_when_desktop_set(self):
        agent = make_agent(desktop=make_sandbox(unit_type="desktop"))
        ctx = make_run_context(agent)
        mock_svc = AsyncMock()
        mock_svc.take_screenshot = AsyncMock(return_value=b"\xff\xd8fake-jpeg")
        from backend.tools.executors.desktop import run_desktop_screenshot

        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=mock_svc,
        ):
            result = await run_desktop_screenshot(ctx, {})
        assert result.image_bytes == b"\xff\xd8fake-jpeg"

    @pytest.mark.asyncio
    async def test_sandbox_tool_ignores_desktop(self):
        """A sandbox tool only checks ctx.agent.sandbox, not desktop."""
        agent = make_agent(
            sandbox=None,
            desktop=make_sandbox(unit_type="desktop"),
        )
        ctx = make_run_context(agent)
        from backend.tools.executors.sandbox import run_sandbox_screenshot

        with pytest.raises(ToolExecutionError) as exc_info:
            await run_sandbox_screenshot(ctx, {})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_desktop_tool_ignores_sandbox(self):
        """A desktop tool only checks ctx.agent.desktop, not sandbox."""
        agent = make_agent(
            sandbox=make_sandbox(unit_type="headless"),
            desktop=None,
        )
        ctx = make_run_context(agent)
        from backend.tools.executors.desktop import run_desktop_mouse_move

        with pytest.raises(ToolExecutionError) as exc_info:
            await run_desktop_mouse_move(ctx, {"x": 10, "y": 20})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE


# ── Section 2: Sandbox Tool Executors ────────────────────────────────────────


class TestSandboxExecutors:
    """Test each of the 12 sandbox tool executor functions."""

    def _ctx_and_svc(self):
        sandbox = make_sandbox()
        agent = make_agent(sandbox=sandbox)
        ctx = make_run_context(agent)
        svc = AsyncMock()
        return ctx, svc, sandbox

    @pytest.mark.asyncio
    async def test_execute_command(self):
        ctx, svc, sandbox = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.sandbox import run_execute_command

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="file.txt", exit_code=0)
        )
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_execute_command(
                ctx, {"command": "ls", "timeout": 30}
            )
        svc.execute_command.assert_awaited_once()
        call_kwargs = svc.execute_command.call_args
        assert "ls" in str(call_kwargs)
        assert str(sandbox.id) in result

    @pytest.mark.asyncio
    async def test_sandbox_start_session(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_start_session

        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_start_session(ctx, {})
        svc.acquire_sandbox_for_agent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sandbox_end_session(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_end_session

        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_end_session(ctx, {})
        svc.release_agent_sandbox.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sandbox_health(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_health

        svc.sandbox_health = AsyncMock(
            return_value={"status": "ok", "uptime_seconds": 99, "display": ":99"}
        )
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_sandbox_health(ctx, {})
        svc.sandbox_health.assert_awaited_once()
        assert "ok" in result.lower() or "status" in result.lower()

    @pytest.mark.asyncio
    async def test_sandbox_screenshot_returns_screenshot_result(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_screenshot

        svc.take_screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_sandbox_screenshot(ctx, {})
        # ScreenshotResult is a dataclass, not a plain string
        assert not isinstance(result, str)
        assert hasattr(result, "image_bytes")
        assert hasattr(result, "media_type")
        assert result.image_bytes == b"\x89PNG\r\n"

    @pytest.mark.asyncio
    async def test_sandbox_mouse_move(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_mouse_move

        svc.mouse_move = AsyncMock(return_value={"ok": True, "x": 50, "y": 75})
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_mouse_move(ctx, {"x": 50, "y": 75})
        svc.mouse_move.assert_awaited_once()
        call_kwargs = svc.mouse_move.call_args
        assert 50 in call_kwargs.args or call_kwargs.kwargs.get("x") == 50

    @pytest.mark.asyncio
    async def test_sandbox_mouse_click(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_mouse_click

        svc.mouse_click = AsyncMock(
            return_value={"ok": True, "x": 100, "y": 200, "button": 1}
        )
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_mouse_click(
                ctx, {"x": 100, "y": 200, "button": 1, "click_type": "single"}
            )
        svc.mouse_click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sandbox_mouse_scroll(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_mouse_scroll

        svc.mouse_scroll = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_mouse_scroll(
                ctx, {"direction": "down", "clicks": 3}
            )
        svc.mouse_scroll.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sandbox_mouse_location(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_mouse_location

        svc.mouse_location = AsyncMock(return_value={"x": 320, "y": 240})
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_sandbox_mouse_location(ctx, {})
        svc.mouse_location.assert_awaited_once()
        assert "320" in result and "240" in result

    @pytest.mark.asyncio
    async def test_sandbox_keyboard_press_with_keys(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_keyboard_press

        svc.keyboard_press = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_keyboard_press(ctx, {"keys": "Return"})
        svc.keyboard_press.assert_awaited_once()
        call_kwargs = svc.keyboard_press.call_args
        # Should pass keys="Return" (not text)
        assert "Return" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_sandbox_keyboard_press_with_text(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_keyboard_press

        svc.keyboard_press = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            await run_sandbox_keyboard_press(ctx, {"text": "hello world"})
        svc.keyboard_press.assert_awaited_once()
        call_kwargs = svc.keyboard_press.call_args
        assert "hello world" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_sandbox_keyboard_press_with_neither_raises(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.sandbox import run_sandbox_keyboard_press

        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=svc,
        ):
            with pytest.raises(ToolExecutionError) as exc_info:
                await run_sandbox_keyboard_press(ctx, {})
            assert exc_info.value.error_code == ToolExecutionError.INVALID_INPUT


# ── Section 3: Desktop Tool Executors ────────────────────────────────────────


class TestDesktopExecutors:
    """Test each of the 10 desktop tool executor functions."""

    def _ctx_and_svc(self):
        desktop = make_sandbox(unit_type="desktop", host="192.168.1.10")
        agent = make_agent(desktop=desktop)
        ctx = make_run_context(agent)
        svc = AsyncMock()
        return ctx, svc, desktop

    @pytest.mark.asyncio
    async def test_desktop_screenshot(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_screenshot

        svc.take_screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_desktop_screenshot(ctx, {})
        assert not isinstance(result, str)
        assert hasattr(result, "image_bytes")
        assert result.image_bytes == b"\x89PNG\r\n"

    @pytest.mark.asyncio
    async def test_desktop_mouse_move(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_mouse_move

        svc.mouse_move = AsyncMock(return_value={"ok": True, "x": 300, "y": 400})
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_mouse_move(ctx, {"x": 300, "y": 400})
        svc.mouse_move.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_desktop_mouse_click(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_mouse_click

        svc.mouse_click = AsyncMock(
            return_value={"ok": True, "x": 50, "y": 60, "button": 3}
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_mouse_click(
                ctx, {"x": 50, "y": 60, "button": 3, "click_type": "double"}
            )
        svc.mouse_click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_desktop_mouse_scroll(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_mouse_scroll

        svc.mouse_scroll = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_mouse_scroll(
                ctx, {"direction": "up", "clicks": 5}
            )
        svc.mouse_scroll.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_desktop_keyboard_press_with_keys(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_keyboard_press

        svc.keyboard_press = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_keyboard_press(ctx, {"keys": "ctrl+c"})
        svc.keyboard_press.assert_awaited_once()
        assert "ctrl+c" in str(svc.keyboard_press.call_args)

    @pytest.mark.asyncio
    async def test_desktop_keyboard_press_with_text(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_keyboard_press

        svc.keyboard_press = AsyncMock(return_value={"ok": True})
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_keyboard_press(ctx, {"text": "typed text"})
        svc.keyboard_press.assert_awaited_once()
        assert "typed text" in str(svc.keyboard_press.call_args)

    @pytest.mark.asyncio
    async def test_desktop_keyboard_press_empty_raises(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.tools.executors.desktop import run_desktop_keyboard_press

        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            with pytest.raises(ToolExecutionError) as exc_info:
                await run_desktop_keyboard_press(ctx, {})
            assert exc_info.value.error_code == ToolExecutionError.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_desktop_open_url(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_open_url

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=0)
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_open_url(ctx, {"url": "https://example.com"})
        svc.execute_command.assert_awaited_once()
        cmd_str = str(svc.execute_command.call_args)
        assert "https://example.com" in cmd_str
        # Should invoke chrome/chromium
        assert "chrom" in cmd_str.lower() or "google" in cmd_str.lower()

    @pytest.mark.asyncio
    async def test_desktop_list_windows(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_list_windows

        svc.execute_command = AsyncMock(
            return_value=ShellResult(
                stdout="0x01 Desktop\n0x02 Terminal", exit_code=0
            )
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_desktop_list_windows(ctx, {})
        svc.execute_command.assert_awaited_once()
        assert "wmctrl" in str(svc.execute_command.call_args)

    @pytest.mark.asyncio
    async def test_desktop_focus_window_by_title(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_focus_window

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=0)
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_focus_window(ctx, {"title": "Terminal"})
        svc.execute_command.assert_awaited_once()
        cmd_str = str(svc.execute_command.call_args)
        assert "wmctrl" in cmd_str
        assert "-a" in cmd_str

    @pytest.mark.asyncio
    async def test_desktop_focus_window_by_window_id(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_focus_window

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=0)
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_focus_window(ctx, {"window_id": "0x04000003"})
        svc.execute_command.assert_awaited_once()
        cmd_str = str(svc.execute_command.call_args)
        assert "wmctrl" in cmd_str
        assert "-i" in cmd_str
        assert "-a" in cmd_str

    @pytest.mark.asyncio
    async def test_desktop_get_clipboard(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_get_clipboard

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="clipboard content", exit_code=0)
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            result = await run_desktop_get_clipboard(ctx, {})
        svc.execute_command.assert_awaited_once()
        assert "xclip" in str(svc.execute_command.call_args)

    @pytest.mark.asyncio
    async def test_desktop_set_clipboard(self):
        ctx, svc, _ = self._ctx_and_svc()
        from backend.services.sandbox_client import ShellResult
        from backend.tools.executors.desktop import run_desktop_set_clipboard

        svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=0)
        )
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=svc,
        ):
            await run_desktop_set_clipboard(ctx, {"content": "paste me"})
        svc.execute_command.assert_awaited_once()
        cmd_str = str(svc.execute_command.call_args)
        assert "xclip" in cmd_str


# ── Section 4: Isolation Tests ───────────────────────────────────────────────


class TestIsolation:
    """Verify sandbox and desktop tools are completely independent."""

    @pytest.mark.asyncio
    async def test_agent_with_sandbox_only(self):
        """Agent with sandbox but no desktop: desktop tools fail, sandbox tools work."""
        agent = make_agent(sandbox=make_sandbox(), desktop=None)
        ctx = make_run_context(agent)
        mock_svc = AsyncMock()
        mock_svc.take_screenshot = AsyncMock(return_value=b"\x89PNG")

        from backend.tools.executors.desktop import run_desktop_screenshot
        from backend.tools.executors.sandbox import run_sandbox_screenshot

        # Desktop tool should fail
        with pytest.raises(ToolExecutionError) as exc_info:
            await run_desktop_screenshot(ctx, {})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE

        # Sandbox tool should succeed
        with patch(
            "backend.tools.executors.sandbox._get_sandbox_service",
            return_value=mock_svc,
        ):
            result = await run_sandbox_screenshot(ctx, {})
        assert hasattr(result, "image_bytes")

    @pytest.mark.asyncio
    async def test_agent_with_desktop_only(self):
        """Agent with desktop but no sandbox: sandbox tools fail, desktop tools work."""
        agent = make_agent(sandbox=None, desktop=make_sandbox(unit_type="desktop"))
        ctx = make_run_context(agent)
        mock_svc = AsyncMock()
        mock_svc.take_screenshot = AsyncMock(return_value=b"\xff\xd8jpeg")

        from backend.tools.executors.desktop import run_desktop_screenshot
        from backend.tools.executors.sandbox import run_sandbox_screenshot

        # Sandbox tool should fail
        with pytest.raises(ToolExecutionError) as exc_info:
            await run_sandbox_screenshot(ctx, {})
        assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE

        # Desktop tool should succeed
        with patch(
            "backend.tools.executors.desktop._get_sandbox_service",
            return_value=mock_svc,
        ):
            result = await run_desktop_screenshot(ctx, {})
        assert hasattr(result, "image_bytes")
