"""
Unit tests for backend.services.sandbox_service.

v3.1: Rewritten for user-owned sandbox model.
  - OrchestratorClient replaces PoolManagerClient
  - SandboxService methods operate on Sandbox objects, not agents
  - Legacy compat shims (ensure_running_sandbox, close_sandbox) tested separately

No real network or database writes — uses the session fixture from conftest.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_service import OrchestratorClient, SandboxMetadata, SandboxService


# ---------------------------------------------------------------------------
# OrchestratorClient
# ---------------------------------------------------------------------------


def _mock_http_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_orchestrator_client_claim() -> None:
    client = OrchestratorClient()
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

        result = await client.claim("abc123", agent_id="agent-001")

    assert result["sandbox_id"] == "abc123"
    assert result["host_port"] == 30001
    assert result["created"] is True


@pytest.mark.asyncio
async def test_orchestrator_client_release() -> None:
    client = OrchestratorClient()
    expected = {"ok": True, "sandbox_id": "abc123"}

    with patch("backend.services.sandbox_service.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_http_response(expected))
        mock_cls.return_value = mock_http

        result = await client.release("abc123")

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_orchestrator_client_health() -> None:
    client = OrchestratorClient()
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
# SandboxMetadata (backward compat dataclass)
# ---------------------------------------------------------------------------


def test_sandbox_metadata_defaults():
    meta = SandboxMetadata(
        sandbox_id="s1",
        agent_id="a1",
        persistent=False,
        status="running",
    )
    assert meta.sandbox_id == "s1"
    assert meta.created is False
    assert meta.restarted is False
    assert meta.previous_sandbox_id is None
    assert meta.message == ""


# ---------------------------------------------------------------------------
# SandboxService — new user-owned methods (mocked)
# ---------------------------------------------------------------------------


def test_sandbox_service_instantiates():
    svc = SandboxService()
    assert svc is not None


# ---------------------------------------------------------------------------
# Legacy compat shims — ensure_running_sandbox, close_sandbox
# ---------------------------------------------------------------------------


def _patch_vm_configured():
    """Patch SandboxService._vm_configured to return True so tests bypass the offline guard."""
    return patch.object(SandboxService, "_vm_configured", return_value=True)


@pytest.mark.asyncio
async def test_ensure_running_returns_offline_when_unconfigured(session, sample_engineer) -> None:
    """When sandbox VM is not configured, returns offline metadata."""
    with patch.object(SandboxService, "_vm_configured", return_value=False):
        svc = SandboxService()
        meta = await svc.ensure_running_sandbox(session, sample_engineer)

    assert meta.status == "offline"
    assert "offline" in meta.sandbox_id


# ---------------------------------------------------------------------------
# SandboxService — screenshot, mouse, keyboard, recording
# (These now take Sandbox objects. We mock the underlying client.)
# ---------------------------------------------------------------------------


def _make_mock_sandbox():
    """Create a mock Sandbox object with the fields the service methods expect."""
    sb = MagicMock()
    sb.id = uuid.uuid4()
    sb.host = "10.0.0.1"
    sb.port = 30001
    sb.auth_token = "tok-test"
    sb.orchestrator_sandbox_id = "orch-sb-001"
    return sb


@pytest.mark.asyncio
async def test_take_screenshot_returns_bytes() -> None:
    sb = _make_mock_sandbox()

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.get_screenshot = AsyncMock(return_value=b"JPEG_BYTES")
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.take_screenshot(sb)

    assert result == b"JPEG_BYTES"


@pytest.mark.asyncio
async def test_mouse_move() -> None:
    sb = _make_mock_sandbox()

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.mouse_move = AsyncMock(return_value={"ok": True, "x": 10, "y": 20})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.mouse_move(sb, 10, 20)

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_keyboard_press_keys() -> None:
    sb = _make_mock_sandbox()

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.keyboard_press = AsyncMock(return_value={"ok": True})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        await svc.keyboard_press(sb, keys="Return")


@pytest.mark.asyncio
async def test_start_and_stop_recording() -> None:
    sb = _make_mock_sandbox()

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.start_recording = AsyncMock(return_value={"ok": True, "status": "started"})
        mock_client.stop_recording = AsyncMock(return_value=b"MP4_DATA")
        mock_gc.return_value = mock_client

        svc = SandboxService()
        start_result = await svc.start_recording(sb)
        stop_result = await svc.stop_recording(sb)

    assert start_result["status"] == "started"
    assert stop_result == b"MP4_DATA"


@pytest.mark.asyncio
async def test_sandbox_health() -> None:
    sb = _make_mock_sandbox()

    with patch("backend.services.sandbox_service.get_sandbox_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value={"status": "ok", "uptime_seconds": 10.0})
        mock_gc.return_value = mock_client

        svc = SandboxService()
        result = await svc.sandbox_health(sb)

    assert result["status"] == "ok"
