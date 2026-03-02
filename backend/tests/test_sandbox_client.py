"""
Unit tests for backend.services.sandbox_client.

All network I/O (WebSocket + httpx) is mocked — no real VM required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_client import (
    SandboxClient,
    SandboxConnection,
    ShellResult,
    get_sandbox_client,
)

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
# SandboxClient — registration
# ---------------------------------------------------------------------------


def test_register_creates_connection() -> None:
    client = SandboxClient()
    client.register("sbox1", "10.0.0.1", 30001, "token-abc")
    conn = client._connections["sbox1"]
    assert conn.rest_base_url == "http://10.0.0.1:30001"
    assert conn.auth_token == "token-abc"


def test_unregister_removes_connection() -> None:
    client = SandboxClient()
    client.register("sbox1", "10.0.0.1", 30001, "tok")
    # Patch asyncio.create_task so the async close() doesn't need a loop
    with patch("backend.services.sandbox_client.asyncio.create_task"):
        client.unregister("sbox1")
    assert "sbox1" not in client._connections


def test_unregister_missing_is_noop() -> None:
    client = SandboxClient()
    with patch("backend.services.sandbox_client.asyncio.create_task"):
        client.unregister("nonexistent")  # must not raise


def test_get_conn_raises_for_unknown_sandbox() -> None:
    client = SandboxClient()
    with pytest.raises(RuntimeError, match="No connection registered"):
        client._get_conn("ghost")


# ---------------------------------------------------------------------------
# SandboxClient — REST operations (httpx mocked)
# ---------------------------------------------------------------------------


def _make_client_with_mock_http(sandbox_id: str = "sbox1") -> tuple[SandboxClient, MagicMock]:
    """Return (SandboxClient, mock_http_client) with sbox1 registered."""
    client = SandboxClient()
    client.register(sandbox_id, "127.0.0.1", 30001, "token")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_http.is_closed = False

    conn = client._connections[sandbox_id]
    conn._http = mock_http
    return client, mock_response


@pytest.mark.asyncio
async def test_health_check_calls_get() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"status": "ok", "uptime_seconds": 42.0})

    result = await client.health_check("sbox1")

    assert result["status"] == "ok"
    conn = client._connections["sbox1"]
    conn._http.get.assert_awaited_once_with("/health")


@pytest.mark.asyncio
async def test_get_screenshot_returns_bytes() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.content = b"JPEG_DATA"

    result = await client.get_screenshot("sbox1")

    assert result == b"JPEG_DATA"
    conn = client._connections["sbox1"]
    conn._http.get.assert_awaited_once_with("/screenshot", timeout=20.0)


@pytest.mark.asyncio
async def test_mouse_move_posts_correct_payload() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"ok": True, "x": 100, "y": 200})

    await client.mouse_move("sbox1", 100, 200)

    conn = client._connections["sbox1"]
    conn._http.post.assert_awaited_once_with("/mouse/move", json={"x": 100, "y": 200})


@pytest.mark.asyncio
async def test_mouse_location_calls_get() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"x": 50, "y": 75})

    result = await client.mouse_location("sbox1")

    assert result == {"x": 50, "y": 75}


@pytest.mark.asyncio
async def test_keyboard_press_with_keys() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"ok": True})

    await client.keyboard_press("sbox1", keys="ctrl+c")

    conn = client._connections["sbox1"]
    conn._http.post.assert_awaited_once_with("/keyboard", json={"keys": "ctrl+c"})


@pytest.mark.asyncio
async def test_keyboard_press_with_text() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"ok": True})

    await client.keyboard_press("sbox1", text="hello world")

    conn = client._connections["sbox1"]
    conn._http.post.assert_awaited_once_with("/keyboard", json={"text": "hello world"})


@pytest.mark.asyncio
async def test_start_recording() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.json = MagicMock(return_value={"ok": True, "status": "started"})

    result = await client.start_recording("sbox1")

    assert result["status"] == "started"
    conn = client._connections["sbox1"]
    conn._http.post.assert_awaited_once_with("/record/start", timeout=10.0)


@pytest.mark.asyncio
async def test_stop_recording_returns_bytes() -> None:
    client, mock_resp = _make_client_with_mock_http()
    mock_resp.content = b"MP4_DATA"

    result = await client.stop_recording("sbox1")

    assert result == b"MP4_DATA"
    conn = client._connections["sbox1"]
    conn._http.post.assert_awaited_once_with("/record/stop", timeout=60.0)


# ---------------------------------------------------------------------------
# SandboxClient — shell execution (WebSocket mocked)
# ---------------------------------------------------------------------------

# Fixed marker so tests can construct known drain/end sentinels (client uses token_hex(8) -> 16 chars)
_TEST_MARKER = "a" * 16
_DRAIN_SENTINEL = f"__AICT_DRAIN_{_TEST_MARKER}__"
_END_SENTINEL = f"__AICT_CMD_DONE_{_TEST_MARKER}__"


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
    """WebSocket mock that uses recv() and a list of payloads (no shared iterator)."""

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
    """
    Shell execution: drain phase sees two sentinels, then read phase gets
    command output and end sentinel. Exit code is parsed.
    """
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")
    fake_ws = _make_fake_ws_drain_then_output(b"hello from sandbox\n")

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell("sbox1", "echo hello", timeout=5.0)

    assert isinstance(result, ShellResult)
    assert "hello from sandbox" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_timeout_returns_none_exit_code() -> None:
    """When shell times out (no end sentinel), exit_code is None."""
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")
    fake_ws = _make_fake_ws_drain_then_hang()

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell("sbox1", "sleep 99", timeout=0.05)

    assert result.exit_code is None


@pytest.mark.asyncio
async def test_execute_shell_drain_waits_for_two_sentinels() -> None:
    """Drain phase does not break after first sentinel (echo); waits for second (real echo)."""
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")
    # One recv with both sentinels (simulates echo then real output)
    drain_data = (f"x\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    command_out = b"ok\n" + f"{_END_SENTINEL}:0\n".encode()
    fake_ws = FakeWS(recv_payloads=[drain_data, command_out])

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell("sbox1", "echo ok", timeout=5.0)

    assert "ok" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_multiple_sequential_calls() -> None:
    """Multiple execute_shell calls each get a new WS and return correct output."""
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")

    def make_ws():
        return _make_fake_ws_drain_then_output(b"result\n")

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("websockets.connect", side_effect=lambda *a, **k: make_ws()),
    ):
        r1 = await client.execute_shell("sbox1", "first", timeout=5.0)
        r2 = await client.execute_shell("sbox1", "second", timeout=5.0)

    assert "result" in r1.stdout
    assert r1.exit_code == 0
    assert "result" in r2.stdout
    assert r2.exit_code == 0


@pytest.mark.asyncio
async def test_execute_shell_truncation_preserves_sentinel() -> None:
    """When output is truncated, we never drop the last chunk so end sentinel is still found."""
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")
    # Small payloads so we can patch max bytes and still have sentinel in last chunk
    drain_data = (f"prompt\n{_DRAIN_SENTINEL}\n{_DRAIN_SENTINEL}\n").encode()
    big_chunk = b"x" * 60
    end_chunk = b"tail\n" + f"{_END_SENTINEL}:0\n".encode()
    fake_ws = FakeWS(recv_payloads=[drain_data, big_chunk, end_chunk])

    with (
        patch("secrets.token_hex", return_value=_TEST_MARKER),
        patch("backend.services.sandbox_client._MAX_SHELL_OUTPUT_BYTES", 100),
        patch("websockets.connect", return_value=fake_ws),
    ):
        result = await client.execute_shell("sbox1", "large", timeout=5.0)

    assert result.truncated is True
    assert result.exit_code == 0
    assert "tail" in result.stdout


# ---------------------------------------------------------------------------
# get_sandbox_client singleton
# ---------------------------------------------------------------------------


def test_get_sandbox_client_returns_singleton() -> None:
    import backend.services.sandbox_client as mod
    # Reset singleton for isolation
    mod._sandbox_client = None
    c1 = get_sandbox_client()
    c2 = get_sandbox_client()
    assert c1 is c2
    mod._sandbox_client = None  # clean up
