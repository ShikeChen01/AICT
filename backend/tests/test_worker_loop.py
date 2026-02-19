"""Unit tests for worker loop helper utilities."""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.e2b_service import LOCAL_FALLBACK_SANDBOX_ERROR, SandboxMetadata
from backend.tools.loop_registry import (
    RunContext,
    _run_execute_command,
    _run_start_sandbox,
    get_tool_defs_for_role,
    parse_tool_uuid,
)
from backend.workers.loop import (
    _assignment_message_for_agent,
    run_inner_loop,
)
from backend.services.session_service import SessionService


def _make_ctx(session, agent) -> RunContext:
    """Build a minimal RunContext sufficient for sandbox/command tool tests."""
    return RunContext(
        db=session,
        agent=agent,
        project=MagicMock(),
        session_id=uuid4(),
        message_service=MagicMock(),
        session_service=MagicMock(),
        task_service=MagicMock(),
        agent_service=MagicMock(),
        agent_msg_repo=MagicMock(),
    )


def test_parse_tool_uuid_valid_required() -> None:
    value = uuid4()
    result = parse_tool_uuid({"target_agent_id": str(value)}, "target_agent_id")
    assert result == value


def test_parse_tool_uuid_invalid_value_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="Invalid UUID for 'target_agent_id'"):
        parse_tool_uuid({"target_agent_id": "not-a-uuid"}, "target_agent_id")


def test_parse_tool_uuid_missing_required_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="'target_agent_id' is required and must be a UUID"):
        parse_tool_uuid({}, "target_agent_id")


def test_parse_tool_uuid_optional_allows_none_or_empty() -> None:
    assert parse_tool_uuid({"session_id": None}, "session_id", required=False) is None
    assert parse_tool_uuid({"session_id": ""}, "session_id", required=False) is None


@pytest.mark.asyncio
async def test_execute_command_tool_handles_local_fallback_sandbox(sample_engineer, session) -> None:
    sample_engineer.sandbox_id = "local-sbox-test"
    ctx = _make_ctx(session, sample_engineer)
    result = await _run_execute_command(ctx, {"command": "pwd"})
    assert result == LOCAL_FALLBACK_SANDBOX_ERROR


def test_tool_defs_include_start_sandbox_for_all_roles() -> None:
    for role in ("manager", "cto", "engineer"):
        tool_names = {tool["name"] for tool in get_tool_defs_for_role(role)}
        assert "start_sandbox" in tool_names


@pytest.mark.asyncio
async def test_execute_command_tool_reports_restart_feedback(sample_engineer, session) -> None:
    metadata = SandboxMetadata(
        sandbox_id="sandbox-new",
        agent_id=str(sample_engineer.id),
        persistent=False,
        status="running",
        restarted=True,
        previous_sandbox_id="sandbox-old",
        message="Sandbox restarted: sandbox-old -> sandbox-new",
    )
    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock(return_value=None)
    mock_proc.exit_code = 0
    mock_proc.stdout = "/home/user/project"
    mock_proc.stderr = ""

    mock_sandbox = MagicMock()
    mock_sandbox.process.start = AsyncMock(return_value=mock_proc)

    ctx = _make_ctx(session, sample_engineer)
    with patch("backend.tools.loop_registry.E2BService.ensure_running_sandbox", AsyncMock(return_value=metadata)):
        with patch("backend.tools.loop_registry.AsyncSandbox") as mock_async_sandbox:
            mock_async_sandbox.connect = AsyncMock(return_value=mock_sandbox)
            result = await _run_execute_command(ctx, {"command": "pwd"})

    assert "Sandbox restarted: sandbox-old -> sandbox-new" in result
    assert "Exit Code: 0" in result
    assert "/home/user/project" in result


@pytest.mark.asyncio
async def test_start_or_refresh_sandbox_tool_returns_created_message(sample_engineer, session) -> None:
    metadata = SandboxMetadata(
        sandbox_id="sandbox-created",
        agent_id=str(sample_engineer.id),
        persistent=False,
        status="running",
        created=True,
        message="Sandbox created: sandbox-created",
    )

    ctx = _make_ctx(session, sample_engineer)
    with patch("backend.tools.loop_registry.E2BService.ensure_running_sandbox", AsyncMock(return_value=metadata)):
        result = await _run_start_sandbox(ctx, {})

    assert result == "Sandbox created: sandbox-created"


@pytest.mark.asyncio
async def test_assignment_message_for_agent_from_active_task(
    sample_engineer, sample_task, session
) -> None:
    sample_task.assigned_agent_id = sample_engineer.id
    sample_task.status = "assigned"
    sample_engineer.current_task_id = sample_task.id
    await session.flush()

    message = await _assignment_message_for_agent(session, sample_engineer)

    assert message is not None
    assert f"Task assigned: {sample_task.title}" in message
    assert f"Task ID: {sample_task.id}" in message


@pytest.mark.asyncio
async def test_run_inner_loop_uses_assignment_context_without_unread_messages(
    sample_engineer, sample_project, sample_task, session, monkeypatch
) -> None:
    sample_task.assigned_agent_id = sample_engineer.id
    sample_task.status = "assigned"
    sample_engineer.current_task_id = sample_task.id
    await session.flush()

    sess = await SessionService(session).create_session(
        sample_engineer.id,
        sample_project.id,
        task_id=sample_task.id,
        trigger_message_id=None,
    )

    monkeypatch.setattr(
        "backend.services.prompt_service.build_system_prompt",
        lambda *_args, **_kwargs: "test prompt",
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.list_by_target_and_status",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.list_by_session",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.create_message",
        AsyncMock(),
    )

    llm_call = AsyncMock(return_value=("", [{"name": "end", "input": {}, "id": "end-1"}]))
    monkeypatch.setattr(
        "backend.services.llm_service.LLMService.chat_completion_with_tools",
        llm_call,
    )

    result = await run_inner_loop(
        sample_engineer,
        sample_project,
        sess.id,
        trigger_message_id=None,
        db=session,
        interrupt_flag=lambda: False,
    )

    assert result == "normal_end"
    assert llm_call.await_count == 1
