"""Unit tests for ToolContext."""

from uuid import uuid4

import pytest

from backend.tools.context import ToolContext


def test_tool_context_creation() -> None:
    agent_id = uuid4()
    project_id = uuid4()
    ctx = ToolContext(
        agent_id=agent_id,
        project_id=project_id,
        sandbox_id="sbox-123",
        repo_url="https://github.com/org/repo",
        agent_role="engineer",
        agent_display_name="Engineer-1",
        project_name="Test Project",
    )
    assert ctx.agent_id == agent_id
    assert ctx.project_id == project_id
    assert ctx.sandbox_id == "sbox-123"
    assert ctx.repo_url == "https://github.com/org/repo"
    assert ctx.agent_role == "engineer"
    assert ctx.agent_display_name == "Engineer-1"
    assert ctx.project_name == "Test Project"


def test_tool_context_immutable() -> None:
    """ToolContext is immutable (frozen dataclass)."""
    import dataclasses
    ctx = ToolContext(
        agent_id=uuid4(),
        project_id=uuid4(),
        sandbox_id=None,
        repo_url="",
        agent_role="manager",
        agent_display_name="GM",
        project_name="P",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.agent_id = uuid4()
