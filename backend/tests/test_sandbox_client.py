"""
Unit tests for backend.services.sandbox_client.

v3.1: SandboxClient is now fully stateless. All methods take
(host, port, auth_token) as parameters. No connection pool,
register/unregister, or SandboxConnection.

All network I/O (WebSocket + httpx) is mocked — no real VM required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_client import SandboxClient, ShellResult


# Test constants
_HOST = "127.0.0.1"
_PORT = 30001
_TOKEN = "tok"

# Fixed marker so tests can construct known drain/end sentinels
_TEST_MARKER = "a" * 16
_DRAIN_SENTINEL = f"__AICT_DRAIN_{_TEST_MARKER}__"
_END_SENTINEL = f"__AICT_CMD_DONE_{_TEST_MARKER}__"


# ---------------------------------------------------------------------------
# ShellResult
# ---------------------------------------------------------------------------


def test_shell_result_str_with_exit_code() -> None:
    r = ShellResult(stdout="hello\nworld", exit_code=0)
    s = str(r)
    assert "hello" in s
    assert "Exit Code: 0" in s


def test_shell_result_str_truncated() -> None:
    r = ShellResult(stdout="data", exit_code=1, truncated=True)
    s = str(r)
    assert "truncated" in s
    assert "data" in s


def test_shell_result_str_no_exit_code() -> None:
    r = ShellResult(stdout="out")
    s = str(r)
    assert "Exit Code" not in s


# ---------------------------------------------------------------------------
# SandboxClient — stateless design
# ---------------------------------------------------------------------------


def test_sandbox_client_is_stateless() -> None:
    """v3.1: SandboxClient has no connection pool or stateful methods."""
    client = SandboxClient()
    assert not hasattr(client, "_connections")
    assert not hasattr(client, "register")
    assert not hasattr(client, "unregister")


# ---------------------------------------------------------------------------
# SandboxClient — REST operations (httpx mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_calls_get() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "ok", "uptime_seconds": 42.0})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.health_check(_HOST, _PORT, _TOKEN)

    assert result["status"] == "ok"
    assert result["uptime_seconds"] == 42.0


@pytest.mark.asyncio
async def test_get_screenshot_returns_bytes() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"JPEG_DATA"

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.get_screenshot(_HOST, _PORT, _TOKEN)

    assert result == b"JPEG_DATA"


@pytest.mark.asyncio
async def test_mouse_move_posts_correct_payload() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ok": True, "x": 100, "y": 200})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.mouse_move(_HOST, _PORT, _TOKEN, 100, 200)

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_mouse_location_calls_get() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"x": 50, "y": 75})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.mouse_location(_HOST, _PORT, _TOKEN)

    assert result == {"x": 50, "y": 75}


@pytest.mark.asyncio
async def test_keyboard_press_with_keys() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ok": True})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.keyboard_press(_HOST, _PORT, _TOKEN, keys="ctrl+c")

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_keyboard_press_with_text() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ok": True})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.keyboard_press(_HOST, _PORT, _TOKEN, text="hello world")

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_start_recording() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ok": True, "status": "started"})

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.start_recording(_HOST, _PORT, _TOKEN)

    assert result["status"] == "started"


@pytest.mark.asyncio
async def test_stop_recording_returns_bytes() -> None:
    client = SandboxClient()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"MP4_DATA"

    with patch("httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_http

        result = await client.stop_recording(_HOST, _PORT, _TOKEN)

    assert result == b"MP4_DATA"


# ---------------------------------------------------------------------------
# SandboxClient — shell execution (WebSocket mocked)
# ---------------------------------------------------------------------------


def _make_fake_ws_drain_then_output(
    output: bytes,
    exit_code: int = 0,
) -> "FakeWS":
    """FakeWS that returns drain data (sentinel x2) then output + end sentinel."""
    drain_data = (f"prompt\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    end_line = f"{_END_SENTINEL}:{exit_code}\n".encode()
    return FakeWS(recv_payloads=[drain_data, output + end_line])


def _make_fake_ws_drain_then_hang() -> "FakeWS":
    """FakeWS that returns drain data then blocks on recv (to trigger timeout)."""
    drain_data = (f"prompt\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    return FakeWS(recv_payloads=[drain_data], hang_after=True)


class FakeWS:
    """WebSocket mock that uses recv() and a list of payloads."""

    def __init__(
        self,
        recv_payloads: list[bytes],
        *,
        hang_after: bool = False,
    ) -> None:
        self._payloads = list(recv_payloads)
        self._index = 0
        self._hang_after = hang_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, data: bytes) -> None:
        pass

    async def recv(self):
        if self._index < len(self._payloads):
            data = self._payloads[self._index]
            self._index += 1
            return data
        if self._hang_after:
            await asyncio.sleep(100)
        return b""


@pytest.mark.asyncio
async def test_execute_shell_returns_output() -> None:
    """Shell execution with drain + output + end sentinel."""
    client = SandboxClient()
    fake_ws = _make_fake_ws_drain_then_output(b"hello from sandbox\n")

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell(_HOST, _PORT, _TOKEN, "echo hello", timeout=5.0)

    assert isinstance(result, ShellResult)
    assert "hello from sandbox" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_timeout_returns_none_exit_code() -> None:
    """When shell times out (no end sentinel), exit_code is None."""
    client = SandboxClient()
    fake_ws = _make_fake_ws_drain_then_hang()

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell(_HOST, _PORT, _TOKEN, "sleep 99", timeout=0.05)

    assert result.exit_code is None


@pytest.mark.asyncio
async def test_execute_shell_drain_waits_for_two_sentinels() -> None:
    """Drain phase does not break after first sentinel."""
    client = SandboxClient()
    drain_data = (f"x\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    command_out = b"ok\n" + f"{_END_SENTINEL}:0\n".encode()
    fake_ws = FakeWS(recv_payloads=[drain_data, command_out])

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell(_HOST, _PORT, _TOKEN, "echo ok", timeout=5.0)

    assert "ok" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_multiple_sequential_calls() -> None:
    """Multiple calls each get a fresh WS."""
    client = SandboxClient()

    def make_ws():
        return _make_fake_ws_drain_then_output(b"result\n")

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", side_effect=lambda *a, **k: make_ws()),
    ):
        r1 = await client.execute_shell(_HOST, _PORT, _TOKEN, "first", timeout=5.0)
        r2 = await client.execute_shell(_HOST, _PORT, _TOKEN, "second", timeout=5.0)

    assert "result" in r1.stdout
    assert r1.exit_code == 0
    assert "result" in r2.stdout
    assert r2.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_truncation_preserves_sentinel() -> None:
    """When output is truncated, end sentinel is still found."""
    client = SandboxClient()
    drain_data = (f"prompt\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    big_chunk = b"x" * 60
    end_chunk = b"tail\n" + f"{_END_SENTINEL}:0\n".encode()
    fake_ws = FakeWS(recv_payloads=[drain_data, big_chunk, end_chunk])

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("backend.services.sandbox_client._MAX_SHELL_OUTPUT_BYTES", 100),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell(_HOST, _PORT, _TOKEN, "large", timeout=5.0)

    assert result.truncated is True
    assert result.exit_code == 0
