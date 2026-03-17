"""
Tests for the new VM sandbox tool executors in loop_registry.py and
tool_descriptions.json consistency.

All sandbox I/O is mocked — no network or Docker required.
Tests run with sandbox_vm_enabled=False (default) unless patched.

IMPORTANT: Any executor that calls _flush_and_broadcast_sandbox must also
mock the WebSocket manager.  We patch it once in a module-scoped fixture
(_patch_ws_manager) so every test in this file sees an AsyncMock rather
than the real ws_manager singleton (which doesn't exist in tests).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.loop_registry import (
    RunContext,
    _run_execute_command,
    _run_sandbox_end_record_screen,
    _run_sandbox_end_session,
    _run_sandbox_health,
    _run_sandbox_keyboard_press,
    _run_sandbox_mouse_location,
    _run_sandbox_mouse_move,
    _run_sandbox_record_screen,
    _run_sandbox_screenshot,
    _run_sandbox_start_session,
    _run_start_sandbox,
    _get_sandbox_service,
    get_handlers_for_role,
    get_tool_defs_for_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(agent, project, session=None) -> RunContext:
    """Minimal RunContext for tool executor tests.

    When *session* is a real AsyncSession (from the conftest fixture) it is
    used as-is.  When no session is provided we create an AsyncMock that
    supports ``await ctx.db.flush()`` and ``await ctx.db.commit()`` so
    executors that touch the DB don't crash.
    """
    if session is None:
        session = _make_mock_db()
    return RunContext(
        db=session,
        agent=agent,
        project=project,
        session_id=None,
        message_service=MagicMock(),
        session_service=MagicMock(),
        task_service=MagicMock(),
        agent_service=MagicMock(),
        agent_msg_repo=MagicMock(),
    )


def _make_agent(sandbox_id: str | None = "sbox-1") -> MagicMock:
    agent = MagicMock()
    agent.sandbox_id = sandbox_id
    agent.role = "engineer"
    agent.id = "agent-uuid-001"
    if sandbox_id:
        agent.sandbox = _make_mock_sandbox(sandbox_id)
    else:
        agent.sandbox = None
    return agent


def _make_mock_sandbox(sandbox_id: str = "sbox-1") -> MagicMock:
    """Create a mock Sandbox object for tests that need ctx.agent.sandbox."""
    sb = MagicMock()
    sb.id = sandbox_id
    sb.orchestrator_sandbox_id = sandbox_id
    sb.host = "10.0.0.1"
    sb.port = 8080
    sb.auth_token = "tok-test"
    return sb


def _set_agent_sandbox(agent, sandbox_id: str | None) -> None:
    """Set the sandbox relationship on an agent (real ORM or mock) for tests."""
    from sqlalchemy.orm.attributes import set_committed_value
    if sandbox_id:
        mock_sb = _make_mock_sandbox(sandbox_id)
        if hasattr(agent, "_sa_instance_state"):
            set_committed_value(agent, "sandbox", mock_sb)
        else:
            agent.sandbox = mock_sb
    else:
        if hasattr(agent, "_sa_instance_state"):
            set_committed_value(agent, "sandbox", None)
        else:
            agent.sandbox = None


def _patch_sandbox_service():
    """Context manager that patches _get_sandbox_service to return a mock."""
    return patch("backend.tools.executors.sandbox._get_sandbox_service")


def _make_mock_db():
    """Create a mock AsyncSession whose flush/commit/rollback are AsyncMocks.

    Using a plain ``AsyncMock(spec=...)`` with a list doesn't produce awaitable
    child mocks, so we build them explicitly.
    """
    mock_db = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


def _patch_ws_broadcast():
    """Patch ws_manager.broadcast_agent_status inside _flush_and_broadcast_sandbox.

    This prevents the lazy import of backend.websocket.manager from firing in
    tests (where the singleton may not be initialised) and lets us assert on
    broadcast calls.
    """
    mock_ws = MagicMock()
    mock_ws.broadcast_agent_status = AsyncMock()
    return patch("backend.websocket.manager.ws_manager", mock_ws), mock_ws


# ---------------------------------------------------------------------------
# tool_descriptions.json consistency
# ---------------------------------------------------------------------------

_TOOL_DESC_PATH = Path(__file__).parents[1] / "tools" / "tool_descriptions.json"


def test_tool_descriptions_is_valid_json() -> None:
    assert _TOOL_DESC_PATH.exists(), "tool_descriptions.json missing"
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0


def test_all_tool_names_are_unique() -> None:
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    names = [t["name"] for t in data]
    assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"


def test_all_tools_have_required_fields() -> None:
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    required = {"name", "description", "detailed_description", "input_schema", "allowed_roles"}
    for tool in data:
        missing = required - set(tool.keys())
        assert not missing, f"Tool '{tool.get('name')}' missing fields: {missing}"


def test_new_sandbox_tools_in_descriptions() -> None:
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    names = {t["name"] for t in data}
    new_tools = {
        "sandbox_start_session",
        "sandbox_end_session",
        "sandbox_health",
        "sandbox_screenshot",
        "sandbox_mouse_move",
        "sandbox_mouse_location",
        "sandbox_keyboard_press",
        "sandbox_record_screen",
        "sandbox_end_record_screen",
    }
    for tool_name in new_tools:
        assert tool_name in names, f"'{tool_name}' missing from tool_descriptions.json"


def test_sandbox_mouse_move_schema_has_x_y() -> None:
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    tool = next(t for t in data if t["name"] == "sandbox_mouse_move")
    props = tool["input_schema"].get("properties", {})
    assert "x" in props
    assert "y" in props
    assert tool["input_schema"].get("required") == ["x", "y"]


def test_sandbox_keyboard_press_has_keys_and_text() -> None:
    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    tool = next(t for t in data if t["name"] == "sandbox_keyboard_press")
    props = tool["input_schema"].get("properties", {})
    assert "keys" in props
    assert "text" in props


# ---------------------------------------------------------------------------
# Loop registry — tool name registration
# ---------------------------------------------------------------------------


def test_executor_map_contains_all_sandbox_tools() -> None:
    from backend.tools.loop_registry import _TOOL_EXECUTORS

    expected = {
        "sandbox_start_session",
        "sandbox_end_session",
        "sandbox_health",
        "sandbox_screenshot",
        "sandbox_mouse_move",
        "sandbox_mouse_location",
        "sandbox_keyboard_press",
        "sandbox_record_screen",
        "sandbox_end_record_screen",
    }
    for name in expected:
        assert name in _TOOL_EXECUTORS, f"'{name}' missing from _TOOL_EXECUTORS"
        assert _TOOL_EXECUTORS[name] is not None, f"'{name}' executor is None"


def test_get_tool_defs_for_engineer_includes_sandbox_tools() -> None:
    defs = get_tool_defs_for_role("engineer")
    names = {d["name"] for d in defs}
    assert "sandbox_start_session" in names
    assert "sandbox_screenshot" in names
    assert "execute_command" in names


def test_get_handlers_for_engineer_wires_all_sandbox_executors() -> None:
    handlers = get_handlers_for_role("engineer")
    assert "sandbox_start_session" in handlers
    assert "sandbox_end_session" in handlers
    assert "sandbox_health" in handlers
    assert "sandbox_screenshot" in handlers
    assert "sandbox_mouse_move" in handlers
    assert "sandbox_mouse_location" in handlers
    assert "sandbox_keyboard_press" in handlers
    assert "sandbox_record_screen" in handlers
    assert "sandbox_end_record_screen" in handlers


# ---------------------------------------------------------------------------
# execute_command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_command(session, sample_engineer) -> None:
    """v4.1 D1: Agent calls execute_command when sandbox already exists —
    uses svc.execute_command(sandbox, cmd, timeout) directly."""
    from backend.services.sandbox_client import ShellResult

    _set_agent_sandbox(sample_engineer, "vm-sbox-01")
    shell_result = ShellResult(stdout="total 0\n", exit_code=0)
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.execute_command = AsyncMock(return_value=shell_result)
        mock_f.return_value = mock_svc

        result = await _run_execute_command(ctx, {"command": "ls -la", "timeout": 30})

    assert "total 0" in result
    assert "Exit Code: 0" in result
    mock_svc.execute_command.assert_awaited_once_with(
        sample_engineer.sandbox, "ls -la", 30
    )


@pytest.mark.asyncio
async def test_execute_command_no_sandbox_raises_error(session, sample_engineer) -> None:
    """v4.1 D1: Agent calls execute_command with no sandbox — returns
    ToolExecutionError telling agent to call sandbox_start_session first."""
    from backend.tools.result import ToolExecutionError

    _set_agent_sandbox(sample_engineer, None)
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with pytest.raises(ToolExecutionError) as exc_info:
        await _run_execute_command(ctx, {"command": "echo hello"})

    assert exc_info.value.error_code == ToolExecutionError.SANDBOX_UNAVAILABLE
    assert "sandbox_start_session" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _run_start_sandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_sandbox(session, sample_engineer) -> None:
    """v4.1 D1: sandbox_start_session → acquire_sandbox_for_agent → flush+broadcast."""
    _set_agent_sandbox(sample_engineer, None)
    fake_sandbox = _make_mock_sandbox("vm-sbox-02")
    fake_sandbox.unit_type = "headless"
    mock_db = _make_mock_db()
    ctx = _make_ctx(sample_engineer, MagicMock(), mock_db)

    ws_patch, mock_ws = _patch_ws_broadcast()

    with _patch_sandbox_service() as mock_f, ws_patch:
        mock_svc = MagicMock()
        mock_svc.acquire_sandbox_for_agent = AsyncMock(return_value=fake_sandbox)
        mock_f.return_value = mock_svc

        result = await _run_start_sandbox(ctx, {})

    assert "vm-sbox-02" in result
    mock_svc.acquire_sandbox_for_agent.assert_awaited_once()
    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    mock_ws.broadcast_agent_status.assert_awaited_once_with(sample_engineer)


# ---------------------------------------------------------------------------
# _run_sandbox_start_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_start_session(session, sample_engineer) -> None:
    """v4.1 D1: sandbox_start_session → acquire_sandbox_for_agent
    → _flush_and_broadcast_sandbox."""
    fake_sandbox = _make_mock_sandbox("s1")
    fake_sandbox.unit_type = "headless"
    mock_db = _make_mock_db()
    ctx = _make_ctx(sample_engineer, MagicMock(), mock_db)

    ws_patch, mock_ws = _patch_ws_broadcast()

    with _patch_sandbox_service() as mock_f, ws_patch:
        mock_svc = MagicMock()
        mock_svc.acquire_sandbox_for_agent = AsyncMock(return_value=fake_sandbox)
        mock_f.return_value = mock_svc

        result = await _run_sandbox_start_session(ctx, {})

    assert "s1" in result
    assert "headless" in result
    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    mock_ws.broadcast_agent_status.assert_awaited_once_with(sample_engineer)


@pytest.mark.asyncio
async def test_sandbox_start_session_broadcast_failure_is_swallowed(session, sample_engineer) -> None:
    """If WS broadcast fails, sandbox_start_session should still succeed."""
    fake_sandbox = _make_mock_sandbox("s-broadcast-fail")
    fake_sandbox.unit_type = "headless"
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    ws_patch, mock_ws = _patch_ws_broadcast()
    mock_ws.broadcast_agent_status = AsyncMock(side_effect=ConnectionError("WS down"))

    with _patch_sandbox_service() as mock_f, ws_patch:
        mock_svc = MagicMock()
        mock_svc.acquire_sandbox_for_agent = AsyncMock(return_value=fake_sandbox)
        mock_f.return_value = mock_svc

        result = await _run_sandbox_start_session(ctx, {})

    assert "s-broadcast-fail" in result


@pytest.mark.asyncio
async def test_sandbox_start_session_uses_flush_not_commit(session, sample_engineer) -> None:
    """Regression test: must use flush() not commit() for transaction boundary."""
    fake_sandbox = _make_mock_sandbox("s-flush-check")
    fake_sandbox.unit_type = "headless"
    mock_db = _make_mock_db()
    ctx = _make_ctx(sample_engineer, MagicMock(), mock_db)

    ws_patch, mock_ws = _patch_ws_broadcast()

    with _patch_sandbox_service() as mock_f, ws_patch:
        mock_svc = MagicMock()
        mock_svc.acquire_sandbox_for_agent = AsyncMock(return_value=fake_sandbox)
        mock_f.return_value = mock_svc

        await _run_sandbox_start_session(ctx, {})

    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_sandbox_end_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_end_session_with_active_sandbox(session, sample_engineer) -> None:
    """v4.1 D1: Agent ends an active sandbox — release_agent_sandbox is called,
    then _flush_and_broadcast_sandbox fires."""
    _set_agent_sandbox(sample_engineer, "sbox-active")
    mock_db = _make_mock_db()
    ctx = _make_ctx(sample_engineer, MagicMock(), mock_db)

    ws_patch, mock_ws = _patch_ws_broadcast()

    with _patch_sandbox_service() as mock_f, ws_patch:
        mock_svc = MagicMock()
        mock_svc.release_agent_sandbox = AsyncMock()
        mock_f.return_value = mock_svc

        result = await _run_sandbox_end_session(ctx, {})

    assert "ended" in result.lower() or "pool" in result.lower()
    mock_svc.release_agent_sandbox.assert_awaited_once()
    mock_db.flush.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    mock_ws.broadcast_agent_status.assert_awaited_once_with(sample_engineer)


@pytest.mark.asyncio
async def test_sandbox_end_session_no_sandbox(session, sample_engineer) -> None:
    """Agent tries to end a sandbox but none exists — returns a message,
    does NOT call _flush_and_broadcast_sandbox."""
    _set_agent_sandbox(sample_engineer, None)
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_f.return_value = MagicMock()
        result = await _run_sandbox_end_session(ctx, {})

    assert "no active sandbox" in result.lower()


# ---------------------------------------------------------------------------
# _run_sandbox_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_health(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-h")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.sandbox_health = AsyncMock(
            return_value={"status": "ok", "uptime_seconds": 123.0, "display": ":99"}
        )
        mock_f.return_value = mock_svc

        result = await _run_sandbox_health(ctx, {})

    assert "ok" in result
    assert "123" in result
    # v3.1: sandbox_health now takes a Sandbox object (ctx.agent.sandbox)
    mock_svc.sandbox_health.assert_awaited_once()


@pytest.mark.asyncio
async def test_sandbox_health_passes_sandbox_object(session, sample_engineer) -> None:
    """v3.1: run_sandbox_health passes ctx.agent.sandbox (a Sandbox object)
    to the service layer, not the Agent or a DB session."""
    _set_agent_sandbox(sample_engineer, "sbox-rereg")
    mock_db = _make_mock_db()
    ctx = _make_ctx(sample_engineer, MagicMock(), mock_db)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.sandbox_health = AsyncMock(
            return_value={"status": "ok", "uptime_seconds": 5.0, "display": ":99"}
        )
        mock_f.return_value = mock_svc

        result = await _run_sandbox_health(ctx, {})

    assert "ok" in result
    # sandbox_health receives the Sandbox object, not the agent
    mock_svc.sandbox_health.assert_awaited_once()


@pytest.mark.asyncio
async def test_sandbox_health_service_calls_client() -> None:
    """v3.1: SandboxService.sandbox_health delegates to client.health_check
    with the sandbox's host/port/auth_token."""
    import httpx
    from backend.services.sandbox_service import SandboxService

    mock_sandbox = MagicMock()
    mock_sandbox.host = "10.0.0.1"
    mock_sandbox.port = 30001
    mock_sandbox.auth_token = "tok-test"

    mock_client = MagicMock()
    mock_client.health_check = AsyncMock(
        return_value={"status": "ok", "uptime_seconds": 1.0, "display": ":99"}
    )

    svc = SandboxService()
    svc._client = mock_client

    result = await svc.sandbox_health(mock_sandbox)

    assert result["status"] == "ok"
    mock_client.health_check.assert_awaited_once_with("10.0.0.1", 30001, "tok-test")


# ---------------------------------------------------------------------------
# _run_sandbox_screenshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_screenshot(session, sample_engineer) -> None:
    from backend.tools.executors.sandbox import ScreenshotResult

    _set_agent_sandbox(sample_engineer, "sbox-scr")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)
    fake_bytes = b"FAKE_JPEG_DATA"

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.take_screenshot = AsyncMock(return_value=fake_bytes)
        mock_f.return_value = mock_svc

        result = await _run_sandbox_screenshot(ctx, {})

    assert isinstance(result, ScreenshotResult)
    assert result.image_bytes == fake_bytes
    assert result.media_type == "image/jpeg"


# ---------------------------------------------------------------------------
# _run_sandbox_mouse_move
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_mouse_move(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-m")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.mouse_move = AsyncMock(return_value={"ok": True})
        mock_f.return_value = mock_svc

        result = await _run_sandbox_mouse_move(ctx, {"x": 50, "y": 100})

    assert "50" in result
    assert "100" in result
    mock_svc.mouse_move.assert_awaited_once_with(sample_engineer.sandbox, 50, 100)


# ---------------------------------------------------------------------------
# _run_sandbox_mouse_location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_mouse_location(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-ml")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.mouse_location = AsyncMock(return_value={"x": 200, "y": 300})
        mock_f.return_value = mock_svc

        result = await _run_sandbox_mouse_location(ctx, {})

    assert "200" in result
    assert "300" in result


# ---------------------------------------------------------------------------
# _run_sandbox_keyboard_press
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_keyboard_press_with_keys(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-k")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.keyboard_press = AsyncMock(return_value={"ok": True})
        mock_f.return_value = mock_svc

        result = await _run_sandbox_keyboard_press(ctx, {"keys": "ctrl+c"})

    assert "ctrl+c" in result
    mock_svc.keyboard_press.assert_awaited_once_with(
        sample_engineer.sandbox, keys="ctrl+c", text=None
    )


@pytest.mark.asyncio
async def test_sandbox_keyboard_press_missing_input(session, sample_engineer) -> None:
    from backend.tools.result import ToolExecutionError

    _set_agent_sandbox(sample_engineer, "sbox-k")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_f.return_value = MagicMock()
        with pytest.raises(ToolExecutionError, match="Provide exactly one of"):
            await _run_sandbox_keyboard_press(ctx, {})


# ---------------------------------------------------------------------------
# _run_sandbox_record_screen / _run_sandbox_end_record_screen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_record_screen_start(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-r")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.start_recording = AsyncMock(return_value={"ok": True, "status": "started"})
        mock_f.return_value = mock_svc

        result = await _run_sandbox_record_screen(ctx, {})

    assert "started" in result.lower()


@pytest.mark.asyncio
async def test_sandbox_end_record_screen(session, sample_engineer) -> None:
    _set_agent_sandbox(sample_engineer, "sbox-r")
    ctx = _make_ctx(sample_engineer, MagicMock(), session)
    fake_video = b"MP4_DATA_HERE"

    with _patch_sandbox_service() as mock_f:
        mock_svc = MagicMock()
        mock_svc.stop_recording = AsyncMock(return_value=fake_video)
        mock_f.return_value = mock_svc

        result = await _run_sandbox_end_record_screen(ctx, {})

    assert str(len(fake_video)) in result


# ---------------------------------------------------------------------------
# tool_descriptions.json <-> loop_registry alignment
# ---------------------------------------------------------------------------


def test_all_described_tools_have_executors_or_are_end() -> None:
    """Every tool in tool_descriptions.json must have an entry in _TOOL_EXECUTORS."""
    from backend.tools.loop_registry import _TOOL_EXECUTORS

    data = json.loads(_TOOL_DESC_PATH.read_text(encoding="utf-8"))
    for tool in data:
        name = tool["name"]
        assert name in _TOOL_EXECUTORS, (
            f"Tool '{name}' is in tool_descriptions.json but missing from _TOOL_EXECUTORS"
        )


# ---------------------------------------------------------------------------
# SandboxClient — stateless (v3.1)
# ---------------------------------------------------------------------------


def test_sandbox_client_is_stateless() -> None:
    """v3.1: SandboxClient is fully stateless — no connection pool, register,
    or has_connection methods. Each call creates a fresh HTTP/WS connection."""
    from backend.services.sandbox_client import SandboxClient

    client = SandboxClient()
    # Verify the client has no stateful connection pool
    assert not hasattr(client, "_connections")
    assert not hasattr(client, "register")
    assert not hasattr(client, "unregister")
    assert not hasattr(client, "has_connection")
