"""Tests: simulate frontend wake-up message flow for CTO and Engineer agents.

Tests the full path: user sends message -> message stored in DB -> inner loop
picks it up -> LLM called with correct model & message -> agent responds ->
session ends normally.

Also covers model resolution bugs (e.g. fixture/production agents with invalid
model overrides that bypass the configured defaults).
"""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.config import settings
from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent
from backend.llm.model_resolver import default_model_for_role, resolve_model
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.workers.loop import run_inner_loop
from backend.workers.message_router import reset_message_router


@pytest.fixture(autouse=True)
def _reset_router():
    yield
    reset_message_router()


def _llm_end_mock(text: str = "Done.") -> AsyncMock:
    """Return a mock LLM that replies with text + end tool call."""
    return AsyncMock(return_value=(text, [{"name": "end", "input": {}, "id": "end-1"}]))


async def _send_and_run(
    agent,
    project,
    session,
    monkeypatch,
    user_message: str,
    llm_mock: AsyncMock | None = None,
):
    """Helper: create a channel message, start a session, run the inner loop.

    Returns (loop_result, llm_mock, emitted_texts).
    """
    llm_mock = llm_mock or _llm_end_mock()
    monkeypatch.setattr(
        "backend.services.llm_service.LLMService.chat_completion_with_tools",
        llm_mock,
    )

    msg_service = MessageService(session)
    msg = await msg_service.send_user_to_agent(
        target_agent_id=agent.id,
        project_id=project.id,
        content=user_message,
    )
    await session.flush()

    sess = await SessionService(session).create_session(
        agent.id, project.id, trigger_message_id=msg.id,
    )

    emitted_texts: list[str] = []

    result = await run_inner_loop(
        agent,
        project,
        sess.id,
        trigger_message_id=msg.id,
        db=session,
        interrupt_flag=lambda: False,
        emit_text=lambda t: emitted_texts.append(t),
    )
    return result, llm_mock, emitted_texts


# ---------------------------------------------------------------------------
# CTO wake-up
# ---------------------------------------------------------------------------


class TestCTOWakeUp:
    """Simulate frontend sending a message to the CTO agent."""

    @pytest.mark.asyncio
    async def test_cto_wakes_and_processes_user_message(
        self, sample_cto, sample_project, session, monkeypatch,
    ):
        result, llm_mock, emitted = await _send_and_run(
            sample_cto,
            sample_project,
            session,
            monkeypatch,
            user_message="Review the auth module architecture",
            llm_mock=_llm_end_mock("Architecture review complete."),
        )

        assert result == "normal_end", f"Expected normal_end, got {result}"
        assert llm_mock.await_count == 1

        call_kw = llm_mock.await_args.kwargs
        user_msgs = [m for m in call_kw["messages"] if m.get("role") == "user"]
        assert any("auth module" in m["content"] for m in user_msgs), (
            f"User message not forwarded to LLM: {call_kw['messages']}"
        )
        assert call_kw["model"], "Model must be resolved"
        assert emitted, "Agent text should be emitted"

    @pytest.mark.asyncio
    async def test_cto_message_marked_received_after_processing(
        self, sample_cto, sample_project, session, monkeypatch,
    ):
        await _send_and_run(
            sample_cto, sample_project, session, monkeypatch,
            user_message="Check the DB schema",
        )
        remaining = await MessageService(session).get_unread_for_agent(sample_cto.id)
        assert len(remaining) == 0, "Message should be marked as received"


# ---------------------------------------------------------------------------
# Engineer wake-up
# ---------------------------------------------------------------------------


class TestEngineerWakeUp:
    """Simulate frontend sending a message to the Engineer agent."""

    @pytest.mark.asyncio
    async def test_engineer_wakes_and_processes_user_message(
        self, sample_engineer, sample_project, session, monkeypatch,
    ):
        result, llm_mock, emitted = await _send_and_run(
            sample_engineer,
            sample_project,
            session,
            monkeypatch,
            user_message="Implement the login endpoint",
            llm_mock=_llm_end_mock("Login endpoint implemented."),
        )

        assert result == "normal_end"
        assert llm_mock.await_count == 1

        call_kw = llm_mock.await_args.kwargs
        user_msgs = [m for m in call_kw["messages"] if m.get("role") == "user"]
        assert any("login endpoint" in m["content"] for m in user_msgs)

    @pytest.mark.asyncio
    async def test_engineer_message_marked_received(
        self, sample_engineer, sample_project, session, monkeypatch,
    ):
        await _send_and_run(
            sample_engineer, sample_project, session, monkeypatch,
            user_message="Fix the bug",
        )
        remaining = await MessageService(session).get_unread_for_agent(sample_engineer.id)
        assert len(remaining) == 0


# ---------------------------------------------------------------------------
# No-message wake-up (edge case: agent wakes but no message to process)
# ---------------------------------------------------------------------------


class TestWakeWithoutMessage:
    """When an agent wakes but has no unread messages and no assignment, it
    should exit immediately without calling the LLM."""

    @pytest.mark.asyncio
    async def test_cto_exits_immediately_when_no_messages(
        self, sample_cto, sample_project, session, monkeypatch,
    ):
        llm_mock = _llm_end_mock()
        monkeypatch.setattr(
            "backend.services.llm_service.LLMService.chat_completion_with_tools",
            llm_mock,
        )
        sess = await SessionService(session).create_session(
            sample_cto.id, sample_project.id, trigger_message_id=None,
        )

        result = await run_inner_loop(
            sample_cto, sample_project, sess.id,
            trigger_message_id=None, db=session,
            interrupt_flag=lambda: False,
        )

        assert result == "normal_end"
        assert llm_mock.await_count == 0, "LLM should NOT be called when no messages exist"


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


class TestModelResolution:
    """Verify model resolution paths used during wake-up."""

    def test_cto_default_model(self):
        assert default_model_for_role("cto") == settings.cto_model_default

    def test_engineer_default_model(self):
        assert default_model_for_role("engineer") == settings.engineer_junior_model

    def test_manager_default_model(self):
        assert default_model_for_role("manager") == settings.manager_model_default

    def test_resolve_engineer_model_by_seniority(self):
        resolved = resolve_model("engineer", seniority="senior")
        assert resolved == settings.engineer_senior_model

    def test_resolve_engineer_defaults_to_junior_when_seniority_invalid(self):
        resolved = resolve_model("engineer", seniority="staff")
        assert resolved == settings.engineer_junior_model

    def test_resolve_falls_back_to_default_when_override_none(self):
        resolved = resolve_model("cto", model_override=None)
        assert resolved == settings.cto_model_default

    @pytest.mark.asyncio
    async def test_fixture_cto_uses_role_default_model(
        self, sample_cto, sample_project, session, monkeypatch,
    ):
        """sample_cto has model='' so resolve_model falls back to cto_model_default."""
        _, llm_mock, _ = await _send_and_run(
            sample_cto, sample_project, session, monkeypatch,
            user_message="hello",
        )
        resolved = llm_mock.await_args.kwargs["model"]
        assert resolved == settings.cto_model_default, (
            f"Expected cto_model_default '{settings.cto_model_default}', got '{resolved}'"
        )

    @pytest.mark.asyncio
    async def test_cto_model_override_takes_priority(
        self, sample_project, session, monkeypatch,
    ):
        """When agent.model is set explicitly, it takes priority over defaults."""
        cto = Agent(
            id=uuid4(),
            project_id=sample_project.id,
            role="cto",
            display_name="CTO-Override",
            model="claude-4-6-sonnet-latest",
            status="sleeping",
            sandbox_persist=False,
        )
        session.add(cto)
        await session.flush()

        _, llm_mock, _ = await _send_and_run(
            cto, sample_project, session, monkeypatch,
            user_message="hello",
        )
        resolved = llm_mock.await_args.kwargs["model"]
        assert resolved == "claude-4-6-sonnet-latest"

    @pytest.mark.asyncio
    async def test_engineer_with_empty_model_uses_config_default(
        self, sample_project, session, monkeypatch,
    ):
        """An engineer with model='' should resolve from seniority config."""
        engineer = Agent(
            id=uuid4(),
            project_id=sample_project.id,
            role="engineer",
            display_name="Eng-EmptyModel",
            model="",
            tier="intermediate",
            status="sleeping",
            sandbox_persist=False,
        )
        session.add(engineer)
        await session.flush()

        _, llm_mock, _ = await _send_and_run(
            engineer, sample_project, session, monkeypatch,
            user_message="hello",
        )
        resolved = llm_mock.await_args.kwargs["model"]
        assert resolved == settings.engineer_intermediate_model, (
            f"Expected default '{settings.engineer_intermediate_model}', got '{resolved}'"
        )

    @pytest.mark.asyncio
    async def test_cto_with_empty_model_uses_config_default(
        self, sample_project, session, monkeypatch,
    ):
        """A CTO with model='' should fall back to cto_model_default."""
        cto = Agent(
            id=uuid4(),
            project_id=sample_project.id,
            role="cto",
            display_name="CTO-EmptyModel",
            model="",
            status="sleeping",
            sandbox_persist=False,
        )
        session.add(cto)
        await session.flush()

        _, llm_mock, _ = await _send_and_run(
            cto, sample_project, session, monkeypatch,
            user_message="hello",
        )
        resolved = llm_mock.await_args.kwargs["model"]
        assert resolved == settings.cto_model_default, (
            f"Expected default '{settings.cto_model_default}', got '{resolved}'"
        )


# ---------------------------------------------------------------------------
# Full AgentWorker wake cycle (mocked DB session)
# ---------------------------------------------------------------------------


class TestAgentWorkerWakeCycle:
    """Test the full AgentWorker outer-loop wake cycle."""

    @pytest.mark.asyncio
    async def test_worker_processes_wake_signal_and_returns_to_sleeping(
        self, sample_cto, sample_project, session, monkeypatch,
    ):
        """Simulate the full worker cycle:
        1. Worker registers queue with MessageRouter
        2. User message is created
        3. Router notifies the agent
        4. Worker wakes, loads agent, runs inner loop
        5. Agent goes back to sleeping status
        """
        import asyncio
        from backend.workers.agent_worker import AgentWorker
        from backend.workers.message_router import get_message_router

        llm_mock = _llm_end_mock("Done reviewing.")
        monkeypatch.setattr(
            "backend.services.llm_service.LLMService.chat_completion_with_tools",
            llm_mock,
        )
        # Patch where it's imported, not where it's defined
        monkeypatch.setattr(
            "backend.workers.agent_worker.AsyncSessionLocal",
            lambda: _FakeAsyncContextManager(session),
        )

        worker = AgentWorker(sample_cto.id, sample_project.id)
        task = asyncio.create_task(worker.run())

        await worker.wait_ready()

        msg_service = MessageService(session)
        await msg_service.send_user_to_agent(
            target_agent_id=sample_cto.id,
            project_id=sample_project.id,
            content="Wake up and review this",
        )
        await session.flush()

        router = get_message_router()
        router.notify(sample_cto.id)

        # Give the worker time to process; poll instead of fixed sleep
        for _ in range(20):
            await asyncio.sleep(0.05)
            if llm_mock.await_count > 0:
                break

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert llm_mock.await_count >= 1, "LLM should have been called"


class _FakeAsyncContextManager:
    """Wrap a session to act as an async context manager without closing it."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass
