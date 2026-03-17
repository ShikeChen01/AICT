"""
Unit tests for backend.services.sandbox_service.

v4.1: User-owned sandbox model with clean agent access paths.
  - OrchestratorClient replaces PoolManagerClient
  - SandboxService methods operate on Sandbox objects, not agents
  - acquire_sandbox_for_agent / release_agent_sandbox for agent lifecycle

No real network or database writes — uses the session fixture from conftest.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.sandbox_service import OrchestratorClient, SandboxService


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
# SandboxService — user-owned methods
# ---------------------------------------------------------------------------


def test_sandbox_service_instantiates():
    svc = SandboxService()
    assert svc is not None


def _patch_vm_configured():
    """Patch SandboxService._vm_configured to return True so tests bypass the offline guard."""
    return patch.object(SandboxService, "_vm_configured", return_value=True)


# ---------------------------------------------------------------------------
# v4.1 — acquire_sandbox_for_agent, release_agent_sandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_sandbox_raises_when_unconfigured(session, sample_engineer) -> None:
    """v4.1 D1: acquire_sandbox_for_agent raises RuntimeError when VM not configured."""
    with patch.object(SandboxService, "_vm_configured", return_value=False):
        svc = SandboxService()
        with pytest.raises(RuntimeError, match="Sandbox VM not configured"):
            await svc.acquire_sandbox_for_agent(session, sample_engineer)


@pytest.mark.asyncio
async def test_acquire_sandbox_returns_existing(session, sample_engineer) -> None:
    """v4.1 D1: If agent already has an assigned sandbox, return it without provisioning."""
    from backend.db.models import Sandbox

    # Create a sandbox assigned to this agent
    sb = Sandbox(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=sample_engineer.project_id,
        name="existing-sb",
        orchestrator_sandbox_id="orch-123",
        unit_type="headless",
        status="assigned",
        host="10.0.0.1",
        port=8080,
        auth_token="tok-test",
        agent_id=sample_engineer.id,
    )
    session.add(sb)
    await session.flush()

    svc = SandboxService()
    result = await svc.acquire_sandbox_for_agent(session, sample_engineer)
    assert result.id == sb.id
    assert sample_engineer.sandbox is not None


@pytest.mark.asyncio
async def test_acquire_sandbox_always_provisions_headless(session, sample_engineer) -> None:
    """v4.1 D2: acquire_sandbox_for_agent always provisions headless, never desktop."""
    svc = SandboxService()

    with _patch_vm_configured(), \
         patch.object(svc, "create_sandbox", new_callable=AsyncMock) as mock_create, \
         patch.object(svc, "assign_to_agent", new_callable=AsyncMock) as mock_assign:

        fake_sb = MagicMock()
        fake_sb.id = uuid.uuid4()
        fake_sb.unit_type = "headless"
        mock_create.return_value = fake_sb
        mock_assign.return_value = fake_sb

        await svc.acquire_sandbox_for_agent(session, sample_engineer)

    # Verify requires_desktop=False was passed
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs.get("requires_desktop") is False


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

    svc = SandboxService()
    mock_client = MagicMock()
    mock_client.get_screenshot = AsyncMock(return_value=b"JPEG_BYTES")
    svc._client = mock_client

    with patch.object(svc, "_resolve_host_port", new_callable=AsyncMock, return_value=(sb.host, sb.port)):
        result = await svc.take_screenshot(sb)

    assert result == b"JPEG_BYTES"


@pytest.mark.asyncio
async def test_mouse_move() -> None:
    sb = _make_mock_sandbox()

    svc = SandboxService()
    mock_client = MagicMock()
    mock_client.mouse_move = AsyncMock(return_value={"ok": True, "x": 10, "y": 20})
    svc._client = mock_client

    with patch.object(svc, "_resolve_host_port", new_callable=AsyncMock, return_value=(sb.host, sb.port)):
        result = await svc.mouse_move(sb, 10, 20)

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_keyboard_press_keys() -> None:
    sb = _make_mock_sandbox()

    svc = SandboxService()
    mock_client = MagicMock()
    mock_client.keyboard_press = AsyncMock(return_value={"ok": True})
    svc._client = mock_client

    with patch.object(svc, "_resolve_host_port", new_callable=AsyncMock, return_value=(sb.host, sb.port)):
        await svc.keyboard_press(sb, keys="Return")


@pytest.mark.asyncio
async def test_start_and_stop_recording() -> None:
    sb = _make_mock_sandbox()

    svc = SandboxService()
    mock_client = MagicMock()
    mock_client.start_recording = AsyncMock(return_value={"ok": True, "status": "started"})
    mock_client.stop_recording = AsyncMock(return_value=b"MP4_DATA")
    svc._client = mock_client

    with patch.object(svc, "_resolve_host_port", new_callable=AsyncMock, return_value=(sb.host, sb.port)):
        start_result = await svc.start_recording(sb)
        stop_result = await svc.stop_recording(sb)

    assert start_result["status"] == "started"
    assert stop_result == b"MP4_DATA"


@pytest.mark.asyncio
async def test_sandbox_health() -> None:
    sb = _make_mock_sandbox()

    svc = SandboxService()
    mock_client = MagicMock()
    mock_client.health_check = AsyncMock(return_value={"status": "ok", "uptime_seconds": 10.0})
    svc._client = mock_client

    with patch.object(svc, "_resolve_host_port", new_callable=AsyncMock, return_value=(sb.host, sb.port)):
        result = await svc.sandbox_health(sb)

    assert result["status"] == "ok"
