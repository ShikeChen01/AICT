"""Backward-compatibility shim for the old LangChain-based tool registry.

The universal agent loop (loop.py + loop_registry.py) is the current architecture.
This module provides legacy get_*_tools() functions for code and tests that
still reference the old registry pattern.

Each returned object exposes a `.name` attribute so that existing assertions
like `{tool.name for tool in get_engineer_tools()}` work without requiring
a full LangChain tool implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.tools.loop_registry import get_tool_defs_for_role


@dataclass
class _ToolStub:
    """Minimal tool descriptor with a .name attribute."""
    name: str


def _stubs_for_role(role: str) -> list[_ToolStub]:
    tool_defs = get_tool_defs_for_role(role)
    # Map current tool names to legacy names where they differ
    _RENAMES = {
        "execute_command": "sandbox_execute_command",
    }
    stubs: list[_ToolStub] = []
    for t in tool_defs:
        name = t.get("name", "")
        stubs.append(_ToolStub(name=_RENAMES.get(name, name)))
    return stubs


def get_engineer_tools() -> list[_ToolStub]:
    return _stubs_for_role("engineer")


def get_cto_tools() -> list[_ToolStub]:
    return _stubs_for_role("cto")


def get_manager_tools() -> list[_ToolStub]:
    return _stubs_for_role("manager")
