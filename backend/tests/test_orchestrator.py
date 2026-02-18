import pytest
from unittest.mock import AsyncMock

try:
    from backend.db.models import Ticket
except ImportError:
    pytest.skip("Legacy Ticket model removed (Agent 1); orchestrator uses ticket tools", allow_module_level=True)

from backend.core.exceptions import InvalidAgentRole
import backend.services.orchestrator as orchestrator_module
from backend.services.orchestrator import OrchestratorService, sandbox_should_persist
from langchain_core.messages import AIMessage, HumanMessage


def test_sandbox_policy_by_role():
    """Test sandbox persistence policy for different roles."""
    assert sandbox_should_persist("gm") is True
    assert sandbox_should_persist("om") is True
    assert sandbox_should_persist("manager") is True
    assert sandbox_should_persist("engineer") is False


def test_sandbox_policy_invalid_role():
    """Test that invalid roles raise an exception."""
    with pytest.raises(InvalidAgentRole):
        sandbox_should_persist("invalid")


@pytest.mark.asyncio
async def test_orchestrator_creates_persistent_sandbox_for_gm(session, sample_gm):
    """Test GM gets persistent sandbox."""
    orchestrator = OrchestratorService()
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, sample_gm)
    assert sandbox.persistent is True
    assert sample_gm.sandbox_id is not None


@pytest.mark.asyncio
async def test_orchestrator_creates_persistent_sandbox_for_manager(session, sample_manager):
    """Test Manager gets persistent sandbox."""
    orchestrator = OrchestratorService()
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, sample_manager)
    assert sandbox.persistent is True
    assert sample_manager.sandbox_id is not None


@pytest.mark.asyncio
async def test_orchestrator_closes_ephemeral_engineer_sandbox(session, sample_engineer):
    """Test engineer sandboxes are ephemeral and can be closed."""
    orchestrator = OrchestratorService()
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, sample_engineer)
    assert sandbox.persistent is False
    assert sample_engineer.sandbox_id is not None

    await orchestrator.close_if_ephemeral(session, sample_engineer)
    assert sample_engineer.sandbox_id is None


@pytest.mark.asyncio
async def test_wake_agent_changes_status(session, sample_manager):
    """Test waking an agent changes status from sleeping to active."""
    orchestrator = OrchestratorService()
    assert sample_manager.status == "sleeping"
    
    await orchestrator.wake_agent(session, sample_manager)
    assert sample_manager.status == "active"
    assert sample_manager.sandbox_id is not None


def test_postgres_conn_string_conversion():
    assert (
        orchestrator_module._to_postgres_conn_string(
            "postgresql+asyncpg://user:pass@localhost:5432/aict"
        )
        == "postgresql://user:pass@localhost:5432/aict"
    )
    assert (
        orchestrator_module._to_postgres_conn_string(
            "postgres+asyncpg://user:pass@localhost:5432/aict"
        )
        == "postgresql://user:pass@localhost:5432/aict"
    )
    assert (
        orchestrator_module._to_postgres_conn_string(
            "postgresql://user:pass@localhost:5432/aict"
        )
        == "postgresql://user:pass@localhost:5432/aict"
    )


@pytest.mark.asyncio
async def test_graph_runtime_initializes_with_memory_when_postgres_disabled(monkeypatch):
    monkeypatch.setattr(orchestrator_module.settings, "graph_persist_postgres", False)
    await orchestrator_module.shutdown_graph_runtime()

    app = await orchestrator_module.initialize_graph_runtime()
    assert app is not None

    await orchestrator_module.shutdown_graph_runtime()


class _DummyState:
    def __init__(self, values):
        self.values = values


class _DummyGraph:
    def __init__(self, final_state):
        self._final_state = final_state

    async def aget_state(self, config):
        return _DummyState(values={})

    async def ainvoke(self, inputs, config=None):
        return self._final_state


@pytest.mark.asyncio
async def test_run_manager_graph_returns_reason_for_empty_messages(session, sample_manager, monkeypatch):
    graph = _DummyGraph(final_state={"messages": []})
    monkeypatch.setattr(orchestrator_module, "get_graph_app", AsyncMock(return_value=graph))
    monkeypatch.setattr(OrchestratorService, "wake_agent", AsyncMock())
    emit_log = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "emit_agent_log", emit_log)

    orchestrator = OrchestratorService()
    result = await orchestrator.run_manager_graph(
        session=session,
        manager=sample_manager,
        user_message="hello",
    )

    assert "Reason code: EMPTY_MESSAGES" in result
    emit_log.assert_awaited()


@pytest.mark.asyncio
async def test_run_manager_graph_returns_reason_when_last_message_not_ai(
    session, sample_manager, monkeypatch
):
    graph = _DummyGraph(final_state={"messages": [HumanMessage(content="user-only")]})
    monkeypatch.setattr(orchestrator_module, "get_graph_app", AsyncMock(return_value=graph))
    monkeypatch.setattr(OrchestratorService, "wake_agent", AsyncMock())
    emit_log = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "emit_agent_log", emit_log)

    orchestrator = OrchestratorService()
    result = await orchestrator.run_manager_graph(
        session=session,
        manager=sample_manager,
        user_message="hello",
    )

    assert "Reason code: LAST_MESSAGE_NOT_AI" in result
    emit_log.assert_awaited()


@pytest.mark.asyncio
async def test_run_manager_graph_returns_reason_for_unsupported_multipart_content(
    session, sample_manager, monkeypatch
):
    graph = _DummyGraph(final_state={"messages": [AIMessage(content=[{"type": "image"}])]})
    monkeypatch.setattr(orchestrator_module, "get_graph_app", AsyncMock(return_value=graph))
    monkeypatch.setattr(OrchestratorService, "wake_agent", AsyncMock())
    emit_log = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "emit_agent_log", emit_log)

    orchestrator = OrchestratorService()
    result = await orchestrator.run_manager_graph(
        session=session,
        manager=sample_manager,
        user_message="hello",
    )

    assert "Reason code: UNSUPPORTED_MULTIPART_CONTENT" in result
    emit_log.assert_awaited()

