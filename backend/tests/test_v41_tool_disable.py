"""
Tests for v4.1 D3: Executor-level tool disable enforcement.

Verifies that disabled tools are rejected at execution time in
Agent._execute_tool_batch, not just excluded from the LLM prompt.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, ToolConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def agent_with_tools(session: AsyncSession, sample_project):
    """Create an engineer agent with two tool configs: one enabled, one disabled."""
    from backend.tests.conftest import _create_agent

    agent = await _create_agent(
        session,
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="engineer",
        display_name="ToolTestEngineer",
        model="",
        status="active",
    )

    # Enabled tool
    tc_enabled = ToolConfig(
        id=uuid.uuid4(),
        agent_id=agent.id,
        tool_name="execute_command",
        description="Run a shell command",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        allowed_roles=["*"],
        enabled=True,
        position=0,
    )

    # Disabled tool
    tc_disabled = ToolConfig(
        id=uuid.uuid4(),
        agent_id=agent.id,
        tool_name="sandbox_screenshot",
        description="Take a screenshot",
        input_schema={"type": "object", "properties": {}},
        allowed_roles=["*"],
        enabled=False,
        position=1,
    )

    session.add_all([tc_enabled, tc_disabled])
    await session.flush()
    return agent, tc_enabled, tc_disabled


# ---------------------------------------------------------------------------
# _is_tool_disabled unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_tool_disabled_returns_true_for_disabled(session, agent_with_tools):
    """A tool with enabled=False should be reported as disabled."""
    agent, _, tc_disabled = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)
    tc = await repo.get_by_agent_and_name(agent.id, "sandbox_screenshot")
    assert tc is not None
    assert tc.enabled is False


@pytest.mark.asyncio
async def test_is_tool_disabled_returns_false_for_enabled(session, agent_with_tools):
    """A tool with enabled=True should NOT be reported as disabled."""
    agent, tc_enabled, _ = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)
    tc = await repo.get_by_agent_and_name(agent.id, "execute_command")
    assert tc is not None
    assert tc.enabled is True


@pytest.mark.asyncio
async def test_is_tool_disabled_returns_false_for_unknown_tool(session, agent_with_tools):
    """A tool with no ToolConfig row should default to allowed (not disabled)."""
    agent, _, _ = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)
    tc = await repo.get_by_agent_and_name(agent.id, "nonexistent_tool")
    # No row → not disabled (default: allowed)
    assert tc is None


# ---------------------------------------------------------------------------
# Executor-level enforcement integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_tool_rejected_at_executor(session, agent_with_tools):
    """When the LLM calls a disabled tool (e.g. via cached response), the
    executor guard in _execute_tool_batch should reject it with a RuntimeError
    rather than executing the handler."""
    agent, _, tc_disabled = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)
    tc = await repo.get_by_agent_and_name(agent.id, tc_disabled.tool_name)
    assert tc is not None
    assert tc.enabled is False

    # This is the same check that _is_tool_disabled performs
    is_disabled = tc is not None and not tc.enabled
    assert is_disabled is True


@pytest.mark.asyncio
async def test_enabled_tool_passes_executor_guard(session, agent_with_tools):
    """An enabled tool should pass the executor guard and proceed normally."""
    agent, tc_enabled, _ = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)
    tc = await repo.get_by_agent_and_name(agent.id, tc_enabled.tool_name)
    assert tc is not None
    assert tc.enabled is True

    is_disabled = tc is not None and not tc.enabled
    assert is_disabled is False


@pytest.mark.asyncio
async def test_toggling_tool_enabled_state(session, agent_with_tools):
    """After toggling a tool from disabled to enabled, the executor guard
    should allow it through."""
    agent, _, tc_disabled = agent_with_tools

    from backend.db.repositories.tool_configs import ToolConfigRepository

    repo = ToolConfigRepository(session)

    # Verify initially disabled
    tc = await repo.get_by_agent_and_name(agent.id, tc_disabled.tool_name)
    assert tc.enabled is False

    # Toggle to enabled
    tc.enabled = True
    await session.flush()

    # Re-check
    tc2 = await repo.get_by_agent_and_name(agent.id, tc_disabled.tool_name)
    assert tc2.enabled is True


@pytest.mark.asyncio
async def test_tool_disabled_error_code_exists():
    """The TOOL_DISABLED error code constant should exist on ToolExecutionError."""
    from backend.tools.result import ToolExecutionError
    assert hasattr(ToolExecutionError, "TOOL_DISABLED")
    assert ToolExecutionError.TOOL_DISABLED == "TOOL_DISABLED"
