"""Unit tests for worker loop helper utilities."""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.config import settings
from backend.services.sandbox_service import SandboxMetadata
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
from backend.core.constants import USER_AGENT_ID


def _make_unread_msg(from_id, project_id, target_id, content="hi"):
    """Build a minimal mock ChannelMessage object."""
    m = MagicMock()
    m.id = uuid4()
    m.from_agent_id = from_id
    m.target_agent_id = target_id
    m.content = content
    m.message_type = "normal"
    return m


def _make_llm_response(model: str = "claude-test", provider: str = "anthropic") -> MagicMock:
    """Build a minimal mock LLMResponse sufficient for loop.py's usage tracking."""
    r = MagicMock()
    r.model = model
    r.provider = provider
    r.input_tokens = 100
    r.output_tokens = 50
    r.request_id = "req-test"
    return r


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
    from backend.tools.result import ToolExecutionError
    with pytest.raises(ToolExecutionError, match="Invalid UUID for 'target_agent_id'"):
        parse_tool_uuid({"target_agent_id": "not-a-uuid"}, "target_agent_id")


def test_parse_tool_uuid_missing_required_raises_runtime_error() -> None:
    from backend.tools.result import ToolExecutionError
    with pytest.raises(ToolExecutionError, match="'target_agent_id' is required and must be a UUID"):
        parse_tool_uuid({}, "target_agent_id")


def test_parse_tool_uuid_optional_allows_none_or_empty() -> None:
    assert parse_tool_uuid({"session_id": None}, "session_id", required=False) is None
    assert parse_tool_uuid({"session_id": ""}, "session_id", required=False) is None


@pytest.mark.asyncio
async def test_execute_command_tool_uses_vm_sandbox(sample_engineer, session) -> None:
    from backend.services.sandbox_client import ShellResult

    sample_engineer.sandbox_id = "vm-sbox-test"
    shell_result = ShellResult(stdout="/home/user\n", exit_code=0)
    ctx = _make_ctx(session, sample_engineer)

    with patch("backend.tools.executors.sandbox._get_sandbox_service") as mock_f:
        mock_svc = MagicMock()
        mock_svc.execute_command = AsyncMock(return_value=shell_result)
        mock_f.return_value = mock_svc

        result = await _run_execute_command(ctx, {"command": "pwd"})

    assert "/home/user" in result
    assert "Exit Code: 0" in result


def test_tool_defs_include_sandbox_tools_for_all_roles() -> None:
    for role in ("manager", "cto", "engineer"):
        tool_names = {tool["name"] for tool in get_tool_defs_for_role(role)}
        assert "sandbox_start_session" in tool_names


def test_tool_defs_include_spawn_engineer_for_manager_and_cto() -> None:
    manager_tools = {tool["name"] for tool in get_tool_defs_for_role("manager")}
    cto_tools = {tool["name"] for tool in get_tool_defs_for_role("cto")}
    engineer_tools = {tool["name"] for tool in get_tool_defs_for_role("engineer")}
    assert "spawn_engineer" in manager_tools
    assert "spawn_engineer" in cto_tools
    assert "spawn_engineer" not in engineer_tools


@pytest.mark.asyncio
async def test_execute_command_tool_reports_sandbox_output(sample_engineer, session) -> None:
    from backend.services.sandbox_client import ShellResult

    sample_engineer.sandbox_id = "sandbox-exec"
    shell_result = ShellResult(stdout="/home/user/project\n", exit_code=0)
    ctx = _make_ctx(session, sample_engineer)

    with patch("backend.tools.executors.sandbox._get_sandbox_service") as mock_f:
        mock_svc = MagicMock()
        mock_svc.execute_command = AsyncMock(return_value=shell_result)
        mock_f.return_value = mock_svc

        result = await _run_execute_command(ctx, {"command": "pwd"})

    assert "Exit Code: 0" in result
    assert "/home/user/project" in result


@pytest.mark.asyncio
async def test_start_sandbox_tool_returns_ready_message(sample_engineer, session) -> None:
    meta = SandboxMetadata(
        sandbox_id="sandbox-created",
        agent_id=str(sample_engineer.id),
        persistent=False,
        status="running",
        created=True,
        message="Sandbox created: sandbox-created",
    )
    ctx = _make_ctx(session, sample_engineer)

    with patch("backend.tools.executors.sandbox._get_sandbox_service") as mock_f:
        mock_svc = MagicMock()
        mock_svc.ensure_running_sandbox = AsyncMock(return_value=meta)
        mock_f.return_value = mock_svc

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

    llm_call = AsyncMock(return_value=("", [{"name": "end", "input": {}, "id": "end-1"}], _make_llm_response()))
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


@pytest.mark.asyncio
async def test_run_inner_loop_resolves_model_from_role_and_seniority(
    sample_engineer, sample_project, session, monkeypatch
) -> None:
    sample_engineer.model = ""
    sample_engineer.tier = "senior"
    monkeypatch.setattr(settings, "engineer_senior_model", "claude-4-6-sonnet-latest")

    sess = await SessionService(session).create_session(
        sample_engineer.id, sample_project.id, trigger_message_id=None
    )

    unread = [_make_unread_msg(USER_AGENT_ID, sample_project.id, sample_engineer.id, "hello")]
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.list_by_target_and_status",
        AsyncMock(return_value=unread),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.mark_received",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.list_by_session",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.create_message",
        AsyncMock(),
    )

    llm_mock = AsyncMock(return_value=("", [{"name": "end", "input": {}, "id": "end-1"}], _make_llm_response()))
    monkeypatch.setattr(
        "backend.services.llm_service.LLMService.chat_completion_with_tools",
        llm_mock,
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
    assert llm_mock.await_count == 1
    assert llm_mock.await_args.kwargs["model"] == "claude-4-6-sonnet-latest"


@pytest.mark.asyncio
async def test_run_inner_loop_normalizes_legacy_tool_name_in_history(
    sample_engineer, sample_project, session, monkeypatch
) -> None:
    """Legacy saved tool name 'execute_command E2B' is normalized before replay."""
    sess = await SessionService(session).create_session(
        sample_engineer.id, sample_project.id, trigger_message_id=None
    )

    unread = [_make_unread_msg(USER_AGENT_ID, sample_project.id, sample_engineer.id, "hello")]
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.list_by_target_and_status",
        AsyncMock(return_value=unread),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.mark_received",
        AsyncMock(),
    )

    history_row = MagicMock()
    history_row.role = "assistant"
    history_row.content = ""
    history_row.tool_input = {
        "__tool_calls__": [
            {"id": "tc-legacy-1", "name": "execute_command E2B", "input": {"command": "pwd"}}
        ]
    }
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.list_past_session_history",
        AsyncMock(return_value=[history_row]),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.create_message",
        AsyncMock(),
    )

    llm_mock = AsyncMock(return_value=("", [{"name": "end", "input": {}, "id": "end-1"}], _make_llm_response()))
    monkeypatch.setattr(
        "backend.services.llm_service.LLMService.chat_completion_with_tools",
        llm_mock,
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
    assert llm_mock.await_count == 1
    captured_messages = llm_mock.await_args.kwargs["messages"]
    assistant_messages = [m for m in captured_messages if m.get("role") == "assistant"]
    assert assistant_messages
    replayed_calls = assistant_messages[0].get("tool_calls") or []
    assert replayed_calls
    assert replayed_calls[0]["name"] == "execute_command"


# ---------------------------------------------------------------------------
# New tests: silent-turn prevention (fallback messages on error/loopbacks)
# ---------------------------------------------------------------------------


def _patch_loop_basics(monkeypatch, unread_msgs, llm_side_effect=None, llm_return=None):
    """Patch the standard inner-loop dependencies used by multiple tests."""
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.list_by_target_and_status",
        AsyncMock(return_value=unread_msgs),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.ChannelMessageRepository.mark_received",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.list_by_session",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "backend.db.repositories.messages.AgentMessageRepository.create_message",
        AsyncMock(),
    )
    llm_mock = AsyncMock(side_effect=llm_side_effect, return_value=llm_return)
    monkeypatch.setattr(
        "backend.services.llm_service.LLMService.chat_completion_with_tools",
        llm_mock,
    )
    return llm_mock


@pytest.mark.asyncio
async def test_llm_error_emits_fallback_message(
    sample_manager, sample_project, session, monkeypatch
) -> None:
    """When LLM raises, loop returns 'error' and emits a fallback channel message to user."""
    unread = [_make_unread_msg(USER_AGENT_ID, sample_project.id, sample_manager.id, "hello")]
    _patch_loop_basics(monkeypatch, unread, llm_side_effect=RuntimeError("API timeout"))

    sess = await SessionService(session).create_session(
        sample_manager.id, sample_project.id, trigger_message_id=None
    )

    emitted_messages = []

    def capture_emit(msg):
        emitted_messages.append(msg)

    result = await run_inner_loop(
        sample_manager,
        sample_project,
        sess.id,
        trigger_message_id=None,
        db=session,
        interrupt_flag=lambda: False,
        emit_agent_message=capture_emit,
    )

    assert result == "error"
    assert len(emitted_messages) == 1
    assert "error" in emitted_messages[0].content.lower() or "API timeout" in emitted_messages[0].content
    assert emitted_messages[0].target_agent_id == USER_AGENT_ID


@pytest.mark.asyncio
async def test_max_loopbacks_emits_fallback_message(
    sample_manager, sample_project, session, monkeypatch
) -> None:
    """When agent repeatedly produces text without tools, loop emits a fallback after MAX_LOOPBACKS."""
    unread = [_make_unread_msg(USER_AGENT_ID, sample_project.id, sample_manager.id, "hello")]
    # Always return text content with no tool calls → triggers loopback every iteration
    _patch_loop_basics(monkeypatch, unread, llm_return=("some thinking text", [], _make_llm_response()))

    sess = await SessionService(session).create_session(
        sample_manager.id, sample_project.id, trigger_message_id=None
    )

    emitted_messages = []

    def capture_emit(msg):
        emitted_messages.append(msg)

    result = await run_inner_loop(
        sample_manager,
        sample_project,
        sess.id,
        trigger_message_id=None,
        db=session,
        interrupt_flag=lambda: False,
        emit_agent_message=capture_emit,
    )

    assert result == "max_loopbacks"
    assert len(emitted_messages) == 1
    assert "unable" in emitted_messages[0].content.lower() or "rephrase" in emitted_messages[0].content.lower()
    assert emitted_messages[0].target_agent_id == USER_AGENT_ID


# ---------------------------------------------------------------------------
# New tests: WorkerManager diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_manager_get_status_before_start() -> None:
    """WorkerManager reports started=False and worker_count=0 before start()."""
    from backend.workers.worker_manager import WorkerManager

    wm = WorkerManager()
    status = wm.get_status()
    assert status["started"] is False
    assert status["worker_count"] == 0
    assert status["agent_ids"] == []


@pytest.mark.asyncio
async def test_notify_unregistered_agent_logs_warning(caplog) -> None:
    """MessageRouter.notify warns when no queue is registered for agent."""
    import logging
    from backend.workers.message_router import MessageRouter

    router = MessageRouter()
    agent_id = uuid4()

    with caplog.at_level(logging.WARNING, logger="backend.workers.message_router"):
        router.notify(agent_id)

    assert any(str(agent_id) in r.message for r in caplog.records)
    assert any("no queue" in r.message.lower() for r in caplog.records)
