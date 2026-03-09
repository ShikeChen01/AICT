"""Tests for backend.tools.registry tool exposure."""

from backend.tools.registry import get_cto_tools, get_engineer_tools, get_manager_tools


def test_sandbox_start_session_available_for_all_roles() -> None:
    manager_names = {tool.name for tool in get_manager_tools()}
    cto_names = {tool.name for tool in get_cto_tools()}
    engineer_names = {tool.name for tool in get_engineer_tools()}

    assert "sandbox_start_session" in manager_names
    assert "sandbox_start_session" in cto_names
    assert "sandbox_start_session" in engineer_names


def test_engineer_has_all_sandbox_tools() -> None:
    engineer_names = {tool.name for tool in get_engineer_tools()}
    expected = {
        "sandbox_start_session",
        "sandbox_end_session",
        "sandbox_execute_command",
        "sandbox_health",
        "sandbox_screenshot",
        "sandbox_mouse_move",
        "sandbox_mouse_click",
        "sandbox_mouse_scroll",
        "sandbox_mouse_location",
        "sandbox_keyboard_press",
        "sandbox_record_screen",
        "sandbox_end_record_screen",
    }
    for name in expected:
        assert name in engineer_names, f"'{name}' missing from engineer tools"


def test_manager_has_sandbox_tools() -> None:
    """All roles (including manager) have sandbox access in the current architecture."""
    manager_names = {tool.name for tool in get_manager_tools()}
    assert "sandbox_execute_command" in manager_names
    assert "sandbox_start_session" in manager_names


def test_no_e2b_tools_in_any_role() -> None:
    for get_tools in (get_manager_tools, get_cto_tools, get_engineer_tools):
        names = {tool.name for tool in get_tools()}
        assert "execute_in_sandbox" not in names, "E2B tool found in registry"
        assert "start_sandbox" not in names, "Deprecated start_sandbox found in registry"
