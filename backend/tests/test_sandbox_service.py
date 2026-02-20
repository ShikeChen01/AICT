"""
Unit tests for backend.services.sandbox_service.

Covers PoolManagerClient (mocked httpx) and SandboxService lifecycle.
No real network or database writes — uses the session fixture from conftest.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_service import PoolManagerClient, SandboxMetadata, SandboxService


# ---------------------------------------------------------------------------
# PoolManagerClient
# ---------------------------------------------------------------------------


def _mock_http_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_pool_manager_client_session_start() -> None:
    client = PoolManagerClient()
    expected = {
        "sandbox_id": "abc123",
        "host_port": 30001,
        "auth_token": "tok-xyz",
        "created": True,
    }

    with patch("backend.services.sandbox_service.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_http_response(expected))
        mock_cls.return_value = mock_http

        result = await client.session_start("agent-001")

    assert result["sandbox_id"] == "abc123"
    assert result["host_port"] == 30001
    assert result["created"] is True


@pytest.mark.asyncio
async def test_pool_manager_client_session_end() -> None:
    client = PoolManagerClient()
    expected = {"ok": True, "sandbox_id": "abc123"}

    with patch("backend.services.sandbox_service.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_http_response(expected))
        mock_cls.return_value = mock_http

        result = await client.session_end("agent-001")

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_pool_manager_client_health() -> None:
    client = PoolManagerClient()
    expected = {
        "status": "ok",
        "total": 3,
        "idle": 2,
        "assigned": 1,
        "unhealthy": 0,
        "max_containers": 7,
        "can_create": True,
    }

    with patch("backend.services.sandbox_service.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_http_response(expected))
        mock_cls.return_value = mock_http

        result = await client.health()

    assert result["status"] == "ok"
    assert result["can_create"] is True


# ---------------------------------------------------------------------------
# SandboxService.ensure_running_sandbox
# ---------------------------------------------------------------------------


def _patch_vm_configured():
    """Patch SandboxService._vm_configured to return True so tests bypass the offline guard."""
    return patch.object(SandboxService, "_vm_configured", return_value=True)


@pytest.mark.asyncio
async def test_ensure_running_creates_new_sandbox(session, sample_engineer) -> None:
    """Agent with no sandbox_id → pool manager creates one."""
    sample_engineer.sandbox_id = None

    pool_response = {
        "sandbox_id": "new-sandbox-01",
        "host_port": 30001,
        "auth_token": "tok-new",
        "created": True,
    }

    with _patch_vm_configured():
        with patch.object(PoolManagerClient, "session_start", AsyncMock(return_value=pool_response)):
            with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
                mock_client = MagicMock()
                mock_client.register = MagicMock()
                mock_gc.return_value = mock_client

                svc = SandboxService()
                meta = await svc.ensure_running_sandbox(session, sample_engineer)

    assert meta.sandbox_id == "new-sandbox-01"
    assert meta.created is True
    assert meta.host_port == 30001
    assert sample_engineer.sandbox_id == "new-sandbox-01"


@pytest.mark.asyncio
async def test_ensure_running_returns_existing_sandbox(session, sample_engineer) -> None:
    """Agent already has a sandbox_id → pool manager returns it, no create."""
    sample_engineer.sandbox_id = "existing-01"

    pool_response = {
        "sandbox_id": "existing-01",
        "host_port": 30010,
        "auth_token": "tok-exist",
        "created": False,
    }

    with _patch_vm_configured():
        with patch.object(PoolManagerClient, "session_start", AsyncMock(return_value=pool_response)):
            with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
                mock_gc.return_value = MagicMock(register=MagicMock())
                svc = SandboxService()
                meta = await svc.ensure_running_sandbox(session, sample_engineer)

    assert meta.created is False
    assert meta.sandbox_id == "existing-01"
    assert meta.restarted is False


@pytest.mark.asyncio
async def test_ensure_running_detects_sandbox_change(session, sample_engineer) -> None:
    """Pool manager returns a different sandbox_id → restarted=True."""
    sample_engineer.sandbox_id = "old-sandbox"

    pool_response = {
        "sandbox_id": "new-sandbox",
        "host_port": 30002,
        "auth_token": "tok-new",
        "created": True,
    }

    with _patch_vm_configured():
        with patch.object(PoolManagerClient, "session_start", AsyncMock(return_value=pool_response)):
            with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
                mock_gc.return_value = MagicMock(register=MagicMock())
                svc = SandboxService()
                meta = await svc.ensure_running_sandbox(session, sample_engineer)

    assert meta.restarted is True
    assert meta.previous_sandbox_id == "old-sandbox"
    assert meta.sandbox_id == "new-sandbox"


@pytest.mark.asyncio
async def test_ensure_running_raises_on_pool_error(session, sample_engineer) -> None:
    """HTTP error from pool manager propagates as RuntimeError."""
    import httpx

    http_error = httpx.HTTPStatusError(
        "Service Unavailable",
        request=MagicMock(),
        response=MagicMock(status_code=503, text="Pool full"),
    )

    with _patch_vm_configured():
        with patch.object(PoolManagerClient, "session_start", AsyncMock(side_effect=http_error)):
            with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
                mock_gc.return_value = MagicMock(register=MagicMock())
                svc = SandboxService()
                with pytest.raises(RuntimeError, match="Pool manager error"):
                    await svc.ensure_running_sandbox(session, sample_engineer)


# ---------------------------------------------------------------------------
# SandboxService.close_sandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_sandbox_releases_and_clears(session, sample_engineer) -> None:
    """close_sandbox calls session_end, unregisters the client, clears sandbox_id."""
    sample_engineer.sandbox_id = "sbox-to-close"

    with patch.object(PoolManagerClient, "session_end", AsyncMock(return_value={"ok": True})):
        with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
            mock_client = MagicMock()
            mock_client.unregister = MagicMock()
            mock_gc.return_value = mock_client

            svc = SandboxService()
            await svc.close_sandbox(session, sample_engineer)

    assert sample_engineer.sandbox_id is None
    mock_client.unregister.assert_called_once_with("sbox-to-close")


@pytest.mark.asyncio
async def test_close_sandbox_raises_when_no_sandbox(session, sample_engineer) -> None:
    from backend.core.exceptions import SandboxNotFoundError

    sample_engineer.sandbox_id = None
    svc = SandboxService()
    with pytest.raises(SandboxNotFoundError):
        await svc.close_sandbox(session, sample_engineer)


# ---------------------------------------------------------------------------
# SandboxService.execute_command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_command_calls_shell(session, sample_engineer) -> None:
    from backend.services.sandbox_client import ShellResult

    sample_engineer.sandbox_id = None

    pool_response = {
        "sandbox_id": "sbox-exec",
        "host_port": 30005,
        "auth_token": "tok-exec",
        "created": True,
    }
    shell_result = ShellResult(stdout="hello world\n", exit_code=0)

    with _patch_vm_configured():
        with patch.object(PoolManagerClient, "session_start", AsyncMock(return_value=pool_response)):
            with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
                mock_client = MagicMock()
                mock_client.register = MagicMock()
                mock_client.execute_shell = AsyncMock(return_value=shell_result)
                mock_gc.return_value = mock_client

                svc = SandboxService()
                result = await svc.execute_command(session, sample_engineer, "echo hello")

    assert result.stdout == "hello world\n"
    assert result.exit_code == 0
    mock_client.execute_shell.assert_awaited_once_with("sbox-exec", "echo hello", timeout=120)


# ---------------------------------------------------------------------------
# SandboxService.take_screenshot / mouse / keyboard / recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_screenshot_returns_bytes(sample_engineer) -> None:
    sample_engineer.sandbox_id = "sbox-shot"

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.get_screenshot = AsyncMock(return_value=b"JPEG_BYTES")
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.take_screenshot(sample_engineer)

    assert result == b"JPEG_BYTES"
    mock_client.get_screenshot.assert_awaited_once_with("sbox-shot")


@pytest.mark.asyncio
async def test_take_screenshot_raises_when_no_sandbox(sample_engineer) -> None:
    from backend.core.exceptions import SandboxNotFoundError

    sample_engineer.sandbox_id = None
    svc = SandboxService()
    with pytest.raises(SandboxNotFoundError):
        await svc.take_screenshot(sample_engineer)


@pytest.mark.asyncio
async def test_mouse_move(sample_engineer) -> None:
    sample_engineer.sandbox_id = "sbox-mouse"

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.mouse_move = AsyncMock(return_value={"ok": True, "x": 10, "y": 20})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.mouse_move(sample_engineer, 10, 20)

    assert result["ok"] is True
    mock_client.mouse_move.assert_awaited_once_with("sbox-mouse", 10, 20)


@pytest.mark.asyncio
async def test_keyboard_press_keys(sample_engineer) -> None:
    sample_engineer.sandbox_id = "sbox-kbd"

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.keyboard_press = AsyncMock(return_value={"ok": True})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        await svc.keyboard_press(sample_engineer, keys="Return")

    mock_client.keyboard_press.assert_awaited_once_with("sbox-kbd", keys="Return", text=None)


@pytest.mark.asyncio
async def test_start_and_stop_recording(sample_engineer) -> None:
    sample_engineer.sandbox_id = "sbox-rec"

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.start_recording = AsyncMock(return_value={"ok": True, "status": "started"})
        mock_client.stop_recording = AsyncMock(return_value=b"MP4_DATA")
        mock_gc.return_value = mock_client

        svc = SandboxService()
        start_result = await svc.start_recording(sample_engineer)
        stop_result = await svc.stop_recording(sample_engineer)

    assert start_result["status"] == "started"
    assert stop_result == b"MP4_DATA"


@pytest.mark.asyncio
async def test_sandbox_health(sample_engineer) -> None:
    sample_engineer.sandbox_id = "sbox-health"

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value={"status": "ok", "uptime_seconds": 10.0})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.sandbox_health(sample_engineer)

    assert result["status"] == "ok"
