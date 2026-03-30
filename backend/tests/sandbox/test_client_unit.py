"""Unit tests for SandboxClient — stateless HTTP client for sandbox operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.sandbox_client import SandboxClient, ShellResult


# ── Constants ────────────────────────────────────────────────────────────────

HOST = "10.0.0.1"
PORT = 8080
TOKEN = "tok-unit-test"
PREFIX = "/api/sandbox/unit-123/proxy"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_httpx_client(*, json_data=None, content=b"", status_code=200):
    """Create a mock httpx.AsyncClient context manager.

    The real SandboxClient uses ``async with httpx.AsyncClient(base_url=..., headers=...)``
    then calls ``client.get(path)`` / ``client.post(path, json=...)``.
    We intercept the AsyncClient constructor and capture calls on the context object.
    """
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {}
    mock_resp.content = content
    mock_resp.text = str(json_data or "")
    if status_code < 400:
        mock_resp.raise_for_status = MagicMock()
    else:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"{status_code}", request=MagicMock(), response=mock_resp,
        )

    ctx = AsyncMock()
    ctx.get = AsyncMock(return_value=mock_resp)
    ctx.post = AsyncMock(return_value=mock_resp)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_cls, ctx


# ── 1. Stateless design ─────────────────────────────────────────────────────

class TestStatelessDesign:
    def test_no_shared_state_between_instances(self):
        a = SandboxClient()
        b = SandboxClient()
        assert a is not b
        # No connection pool or mutable state to share
        assert not hasattr(a, "_pool") and not hasattr(a, "_session")

    def test_no_persistent_connection_pool(self):
        client = SandboxClient()
        attrs = vars(client) if hasattr(client, "__dict__") else {}
        # Should have no instance-level connection-pool attributes
        for key in attrs:
            assert "pool" not in key.lower()


# ── 2. _base_url ────────────────────────────────────────────────────────────

class TestBaseUrl:
    def test_format(self):
        assert SandboxClient._base_url("my-host", 9090) == "http://my-host:9090"

    def test_with_ip(self):
        assert SandboxClient._base_url("192.168.1.1", 443) == "http://192.168.1.1:443"


# ── 3. REST methods — verb, path, payload, auth ─────────────────────────────

class TestRestMethods:
    """Each test patches httpx.AsyncClient to verify the outgoing request.

    The real client uses ``base_url`` on AsyncClient, so ``get``/``post``
    receive a relative path like ``/health`` or ``/mouse/move``.  We verify
    the path and the constructor's ``base_url`` + ``headers`` separately.
    """

    @pytest.mark.asyncio
    async def test_health_check(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"status": "ok"})
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().health_check(HOST, PORT, TOKEN)

        # Constructor receives base_url + auth header
        init_kwargs = mock_cls.call_args[1]
        assert init_kwargs["base_url"] == f"http://{HOST}:{PORT}"
        assert init_kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
        # GET /health
        ctx.get.assert_called_once()
        assert ctx.get.call_args[0][0] == "/health"
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_get_screenshot_returns_bytes(self):
        png_bytes = b"\x89PNG fake screenshot"
        mock_cls, ctx = _mock_httpx_client(content=png_bytes)
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().get_screenshot(HOST, PORT, TOKEN)

        ctx.get.assert_called_once()
        assert "/screenshot" in ctx.get.call_args[0][0]
        assert result == png_bytes

    @pytest.mark.asyncio
    async def test_mouse_move(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_move(HOST, PORT, TOKEN, 150, 300)

        ctx.post.assert_called_once()
        assert ctx.post.call_args[0][0] == "/mouse/move"
        payload = ctx.post.call_args[1]["json"]
        assert payload["x"] == 150
        assert payload["y"] == 300

    @pytest.mark.asyncio
    async def test_mouse_click_with_defaults(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_click(HOST, PORT, TOKEN)

        ctx.post.assert_called_once()
        assert ctx.post.call_args[0][0] == "/mouse/click"
        payload = ctx.post.call_args[1]["json"]
        assert payload["button"] == 1
        assert payload["click_type"] == "single"

    @pytest.mark.asyncio
    async def test_mouse_click_with_custom_args(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_click(
                HOST, PORT, TOKEN, x=50, y=75, button=3, click_type="double",
            )

        payload = ctx.post.call_args[1]["json"]
        assert payload["x"] == 50
        assert payload["y"] == 75
        assert payload["button"] == 3
        assert payload["click_type"] == "double"

    @pytest.mark.asyncio
    async def test_mouse_click_omits_none_coords(self):
        """When x/y are None they should not appear in payload."""
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_click(HOST, PORT, TOKEN)

        payload = ctx.post.call_args[1]["json"]
        assert "x" not in payload
        assert "y" not in payload

    @pytest.mark.asyncio
    async def test_mouse_scroll(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_scroll(
                HOST, PORT, TOKEN, x=10, y=20, direction="up", clicks=5,
            )

        assert ctx.post.call_args[0][0] == "/mouse/scroll"
        payload = ctx.post.call_args[1]["json"]
        assert payload["direction"] == "up"
        assert payload["clicks"] == 5
        assert payload["x"] == 10
        assert payload["y"] == 20

    @pytest.mark.asyncio
    async def test_mouse_location(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"x": 42, "y": 99})
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().mouse_location(HOST, PORT, TOKEN)

        ctx.get.assert_called_once()
        assert ctx.get.call_args[0][0] == "/mouse/location"
        assert result == {"x": 42, "y": 99}

    @pytest.mark.asyncio
    async def test_keyboard_press_with_keys(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().keyboard_press(HOST, PORT, TOKEN, keys="ctrl+c")

        assert ctx.post.call_args[0][0] == "/keyboard"
        payload = ctx.post.call_args[1]["json"]
        # keys should be passed as a string, not an array
        assert payload["keys"] == "ctrl+c"
        assert isinstance(payload["keys"], str)

    @pytest.mark.asyncio
    async def test_keyboard_press_with_text(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().keyboard_press(HOST, PORT, TOKEN, text="hello world")

        payload = ctx.post.call_args[1]["json"]
        assert payload["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_start_recording(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"status": "recording"})
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().start_recording(HOST, PORT, TOKEN)

        assert ctx.post.call_args[0][0] == "/record/start"
        assert result == {"status": "recording"}

    @pytest.mark.asyncio
    async def test_stop_recording_returns_bytes(self):
        mp4_bytes = b"\x00\x00\x00\x1cftypisom"
        mock_cls, ctx = _mock_httpx_client(content=mp4_bytes)
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().stop_recording(HOST, PORT, TOKEN)

        assert ctx.post.call_args[0][0] == "/record/stop"
        assert result == mp4_bytes


# ── 4. path_prefix routing ──────────────────────────────────────────────────

class TestPathPrefixRouting:
    """All methods must prepend path_prefix to the URL path passed to get/post."""

    @pytest.mark.asyncio
    async def test_health_check_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"status": "ok"})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().health_check(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.get.call_args[0][0] == f"{PREFIX}/health"

    @pytest.mark.asyncio
    async def test_screenshot_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(content=b"img")
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().get_screenshot(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.get.call_args[0][0] == f"{PREFIX}/screenshot"

    @pytest.mark.asyncio
    async def test_mouse_move_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_move(HOST, PORT, TOKEN, 0, 0, path_prefix=PREFIX)

        assert ctx.post.call_args[0][0] == f"{PREFIX}/mouse/move"

    @pytest.mark.asyncio
    async def test_keyboard_press_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().keyboard_press(
                HOST, PORT, TOKEN, keys="enter", path_prefix=PREFIX,
            )

        assert ctx.post.call_args[0][0] == f"{PREFIX}/keyboard"

    @pytest.mark.asyncio
    async def test_mouse_click_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_click(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.post.call_args[0][0] == f"{PREFIX}/mouse/click"

    @pytest.mark.asyncio
    async def test_mouse_scroll_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"ok": True})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_scroll(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.post.call_args[0][0] == f"{PREFIX}/mouse/scroll"

    @pytest.mark.asyncio
    async def test_mouse_location_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"x": 0, "y": 0})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().mouse_location(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.get.call_args[0][0] == f"{PREFIX}/mouse/location"

    @pytest.mark.asyncio
    async def test_start_recording_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(json_data={"status": "recording"})
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().start_recording(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.post.call_args[0][0] == f"{PREFIX}/record/start"

    @pytest.mark.asyncio
    async def test_stop_recording_with_prefix(self):
        mock_cls, ctx = _mock_httpx_client(content=b"vid")
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().stop_recording(HOST, PORT, TOKEN, path_prefix=PREFIX)

        assert ctx.post.call_args[0][0] == f"{PREFIX}/record/stop"


# ── 5. Shell REST execution ─────────────────────────────────────────────────

class TestShellExecution:
    @pytest.mark.asyncio
    async def test_shell_rest_success(self):
        mock_cls, ctx = _mock_httpx_client(
            json_data={"stdout": "hello\n", "exit_code": 0, "truncated": False},
        )
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().execute_shell(
                HOST, PORT, TOKEN, "echo hello", timeout=30,
            )

        # Verify request
        ctx.post.assert_called_once()
        assert ctx.post.call_args[0][0] == "/shell/execute"
        payload = ctx.post.call_args[1]["json"]
        assert payload["command"] == "echo hello"
        assert payload["timeout"] == 30

        # Verify parsed result
        assert isinstance(result, ShellResult)
        assert result.stdout == "hello\n"
        assert result.exit_code == 0
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_shell_rest_nonzero_exit(self):
        mock_cls, ctx = _mock_httpx_client(
            json_data={"stdout": "error msg", "exit_code": 127, "truncated": False},
        )
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().execute_shell(HOST, PORT, TOKEN, "bad-cmd")

        assert result.exit_code == 127

    @pytest.mark.asyncio
    async def test_shell_with_path_prefix(self):
        mock_cls, ctx = _mock_httpx_client(
            json_data={"stdout": "", "exit_code": 0, "truncated": False},
        )
        with patch("httpx.AsyncClient", mock_cls):
            await SandboxClient().execute_shell(
                HOST, PORT, TOKEN, "ls", path_prefix=PREFIX,
            )

        assert ctx.post.call_args[0][0] == f"{PREFIX}/shell/execute"


# ── 6. Shell REST timeout (408) ─────────────────────────────────────────────

class TestShellTimeout:
    @pytest.mark.asyncio
    async def test_408_returns_none_exit_code(self):
        """A 408 response is handled gracefully — not raised as an error."""
        mock_cls, ctx = _mock_httpx_client(
            status_code=408,
            json_data={"stdout": "partial output", "exit_code": None},
        )
        with patch("httpx.AsyncClient", mock_cls):
            result = await SandboxClient().execute_shell(
                HOST, PORT, TOKEN, "sleep 999", timeout=1,
            )

        assert result.exit_code is None
        assert "partial output" in result.stdout


# ── 7. ShellResult.__str__ ──────────────────────────────────────────────────

class TestShellResultStr:
    def test_normal_output(self):
        r = ShellResult(stdout="hello world", exit_code=0, truncated=False)
        s = str(r)
        assert "hello world" in s
        assert "0" in s

    def test_truncated_output(self):
        r = ShellResult(stdout="partial...", exit_code=0, truncated=True)
        s = str(r)
        assert "truncat" in s.lower()

    def test_none_exit_code(self):
        r = ShellResult(stdout="timed out", exit_code=None, truncated=True)
        s = str(r)
        # Should represent the absent exit code somehow
        assert "timed out" in s

    def test_nonzero_exit_code(self):
        r = ShellResult(stdout="err", exit_code=1, truncated=False)
        s = str(r)
        assert "1" in s
