"""Shared fixtures for sandbox / desktop test suite."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.services.sandbox_client import SandboxClient, ShellResult
from backend.tools.base import RunContext


# ── Fake Sandbox model ────────────────────────────────────────────────────────

def make_sandbox(
    *,
    unit_type: str = "headless",
    host: str = "10.0.0.1",
    port: int = 8080,
    auth_token: str = "tok-test",
    orchestrator_sandbox_id: str | None = None,
    agent_id=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        unit_type=unit_type,
        host=host,
        port=port,
        auth_token=auth_token,
        orchestrator_sandbox_id=orchestrator_sandbox_id or f"orch-{uuid4().hex[:8]}",
        agent_id=agent_id or uuid4(),
        status="ready",
    )


def make_agent(*, sandbox=None, desktop=None, project_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        project_id=project_id or uuid4(),
        sandbox=sandbox,
        desktop=desktop,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def headless_sandbox():
    return make_sandbox(unit_type="headless")


@pytest.fixture
def desktop_sandbox():
    return make_sandbox(
        unit_type="desktop",
        host="192.168.100.10",
        port=8080,
        orchestrator_sandbox_id="desk-abc123",
    )


@pytest.fixture
def agent_with_sandbox(headless_sandbox):
    return make_agent(sandbox=headless_sandbox)


@pytest.fixture
def agent_with_desktop(desktop_sandbox):
    return make_agent(desktop=desktop_sandbox)


@pytest.fixture
def agent_with_both(headless_sandbox, desktop_sandbox):
    return make_agent(sandbox=headless_sandbox, desktop=desktop_sandbox)


@pytest.fixture
def bare_agent():
    return make_agent()


@pytest.fixture
def mock_sandbox_service():
    svc = AsyncMock()
    svc.take_screenshot = AsyncMock(return_value=b"\xff\xd8fake-jpeg")
    svc.mouse_move = AsyncMock(return_value={"ok": True, "x": 100, "y": 200})
    svc.mouse_click = AsyncMock(return_value={"ok": True, "x": 100, "y": 200, "button": 1})
    svc.mouse_scroll = AsyncMock(return_value={"ok": True})
    svc.mouse_location = AsyncMock(return_value={"x": 100, "y": 200})
    svc.keyboard_press = AsyncMock(return_value={"ok": True})
    svc.execute_command = AsyncMock(return_value=ShellResult(stdout="output", exit_code=0))
    svc.sandbox_health = AsyncMock(return_value={"status": "ok", "uptime_seconds": 42, "display": ":99"})
    svc.start_recording = AsyncMock(return_value={"status": "recording"})
    svc.stop_recording = AsyncMock(return_value=b"\x00\x00fake-mp4")
    svc.acquire_sandbox_for_agent = AsyncMock()
    svc.release_agent_sandbox = AsyncMock()
    return svc


def make_run_context(agent, db=None) -> RunContext:
    return RunContext(
        agent=agent,
        db=db or AsyncMock(),
        project=SimpleNamespace(id=uuid4(), name="test-project"),
        session_id=uuid4(),
        message_service=AsyncMock(),
        session_service=AsyncMock(),
        task_service=AsyncMock(),
        agent_service=AsyncMock(),
        agent_msg_repo=AsyncMock(),
    )


# ── Real VM config (for E2E smoke tests) ──────────────────────────────────────

POOL_MANAGER_HOST = "34.172.85.22"
POOL_MANAGER_PORT = 9090
POOL_MANAGER_TOKEN = "a00bcf5c4e9db40648bc2c0f767e6d3ef682561a93d46602c613b016cc27e557"
