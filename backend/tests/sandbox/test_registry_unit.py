"""Unit tests for the tool registry (loop_registry) — sandbox/desktop registration and availability."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools.loop_registry import (
    _DESKTOP_TOOL_NAMES,
    _SANDBOX_TOOL_NAMES,
    _TOOL_EXECUTORS,
    _sandbox_available,
    get_tool_defs_for_role,
)


# ── Section 1: Tool Set Registration ────────────────────────────────────────


EXPECTED_SANDBOX_TOOLS = {
    "sandbox_start_session",
    "sandbox_end_session",
    "sandbox_health",
    "execute_command",
    "sandbox_screenshot",
    "sandbox_mouse_move",
    "sandbox_mouse_click",
    "sandbox_mouse_scroll",
    "sandbox_mouse_location",
    "sandbox_keyboard_press",
    "sandbox_record_screen",
    "sandbox_end_record_screen",
}

EXPECTED_DESKTOP_TOOLS = {
    "desktop_screenshot",
    "desktop_mouse_move",
    "desktop_mouse_click",
    "desktop_mouse_scroll",
    "desktop_keyboard_press",
    "desktop_open_url",
    "desktop_list_windows",
    "desktop_focus_window",
    "desktop_get_clipboard",
    "desktop_set_clipboard",
}


class TestToolSetRegistration:
    """Verify the correct tools are registered in the right sets."""

    def test_all_12_sandbox_tools_registered(self):
        assert len(_SANDBOX_TOOL_NAMES) == 12
        assert _SANDBOX_TOOL_NAMES == EXPECTED_SANDBOX_TOOLS

    def test_all_10_desktop_tools_registered(self):
        assert len(_DESKTOP_TOOL_NAMES) == 10
        assert _DESKTOP_TOOL_NAMES == EXPECTED_DESKTOP_TOOLS

    def test_no_overlap_between_sandbox_and_desktop(self):
        overlap = _SANDBOX_TOOL_NAMES & _DESKTOP_TOOL_NAMES
        assert overlap == set(), f"Unexpected overlap: {overlap}"

    def test_every_sandbox_desktop_tool_has_executor(self):
        all_compute_tools = _SANDBOX_TOOL_NAMES | _DESKTOP_TOOL_NAMES
        for tool_name in all_compute_tools:
            assert tool_name in _TOOL_EXECUTORS, (
                f"Tool '{tool_name}' has no executor entry"
            )
            assert _TOOL_EXECUTORS[tool_name] is not None, (
                f"Tool '{tool_name}' executor is None"
            )


# ── Section 2: _sandbox_available ────────────────────────────────────────────


class TestSandboxAvailable:
    """Verify the _sandbox_available() check for host configuration."""

    def test_returns_false_when_no_host_configured(self):
        with patch("backend.config.settings") as mock_settings:
            mock_settings.sandbox_orchestrator_host = None
            mock_settings.sandbox_vm_host = None
            assert _sandbox_available() is False

    def test_returns_true_when_sandbox_vm_host_is_set(self):
        with patch("backend.config.settings") as mock_settings:
            mock_settings.sandbox_orchestrator_host = None
            mock_settings.sandbox_vm_host = "10.0.0.5"
            assert _sandbox_available() is True


# ── Section 3: get_tool_defs_for_role ────────────────────────────────────────


class TestGetToolDefsForRole:
    """Verify tool definitions returned by role respect sandbox availability."""

    def test_excludes_sandbox_desktop_tools_when_unavailable(self):
        with patch(
            "backend.tools.loop_registry._sandbox_available", return_value=False
        ):
            defs = get_tool_defs_for_role("engineer")
        tool_names = {d["name"] for d in defs}
        assert tool_names.isdisjoint(_SANDBOX_TOOL_NAMES), (
            f"Sandbox tools should be excluded but found: "
            f"{tool_names & _SANDBOX_TOOL_NAMES}"
        )
        assert tool_names.isdisjoint(_DESKTOP_TOOL_NAMES), (
            f"Desktop tools should be excluded but found: "
            f"{tool_names & _DESKTOP_TOOL_NAMES}"
        )

    def test_includes_sandbox_desktop_tools_when_available(self):
        with patch(
            "backend.tools.loop_registry._sandbox_available", return_value=True
        ):
            defs = get_tool_defs_for_role("engineer")
        tool_names = {d["name"] for d in defs}
        # All sandbox & desktop tools should be present for engineer role
        assert _SANDBOX_TOOL_NAMES.issubset(tool_names), (
            f"Missing sandbox tools: {_SANDBOX_TOOL_NAMES - tool_names}"
        )
        assert _DESKTOP_TOOL_NAMES.issubset(tool_names), (
            f"Missing desktop tools: {_DESKTOP_TOOL_NAMES - tool_names}"
        )
