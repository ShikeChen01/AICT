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


@pytest.mark.asyncio
async def test_execute_shell_returns_output() -> None:
    """
    Shell execution collects stdout. The FakeWS yields normal output then
    hangs, letting the client time out cleanly and return what it got.
    Exit-code parsing (sentinel detection) is tested at the integration level.
    """
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")

    class FakeWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, data):
            pass  # accept but ignore

        def __aiter__(self):
            return self._stream()

        async def _stream(self):
            yield b"hello from sandbox\n"
            # Never yield sentinel — client will time out
            await asyncio.sleep(100)

    with patch("websockets.connect", return_value=FakeWS()):
        result = await client.execute_shell("sbox1", "echo hello", timeout=0.1)

    assert isinstance(result, ShellResult)
    assert "hello from sandbox" in result.stdout
    # exit_code is None because we never sent the sentinel (timed out)
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_execute_shell_timeout_returns_none_exit_code() -> None:
    """When shell times out, exit_code is None."""
    client = SandboxClient()
    client.register("sbox1", "127.0.0.1", 30001, "tok")

    class FakeWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, data):
            pass

        def __aiter__(self):
            return self._stream()

        async def _stream(self):
            # Never yield the sentinel — causes timeout
            await asyncio.sleep(100)
            yield b""

    with patch("websockets.connect", return_value=FakeWS()):
        result = await client.execute_shell("sbox1", "sleep 99", timeout=0.01)

    assert result.exit_code is None


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
