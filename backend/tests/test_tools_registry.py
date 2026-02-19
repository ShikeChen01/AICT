"""Tests for backend.tools.registry tool exposure."""

from backend.tools.registry import get_cto_tools, get_engineer_tools, get_manager_tools


def test_start_sandbox_available_for_all_roles() -> None:
    manager_names = {tool.name for tool in get_manager_tools()}
    cto_names = {tool.name for tool in get_cto_tools()}
    engineer_names = {tool.name for tool in get_engineer_tools()}

    assert "start_sandbox" in manager_names
    assert "start_sandbox" in cto_names
    assert "start_sandbox" in engineer_names
