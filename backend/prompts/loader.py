"""
Load prompt block files from the blocks/ directory at import time.

All blocks are plain text (.md) files. They are read once and cached as module-level
constants. A server restart is required to pick up changes.
"""

from __future__ import annotations

from pathlib import Path

_BLOCKS_DIR = Path(__file__).parent / "blocks"


def _load(filename: str) -> str:
    return (_BLOCKS_DIR / filename).read_text(encoding="utf-8")


# Shared blocks (no placeholders -- do NOT call .format() on these)
RULES_BLOCK: str = _load("rules.md")
THINKING_BLOCK: str = _load("thinking.md")
TOOL_IO_BASE_BLOCK: str = _load("tool_io_base.md")
TOOL_IO_MANAGER_BLOCK: str = _load("tool_io_manager.md")
TOOL_IO_CTO_BLOCK: str = _load("tool_io_cto.md")
TOOL_IO_ENGINEER_BLOCK: str = _load("tool_io_engineer.md")
LOOPBACK_BLOCK: str = _load("loopback.md")
SUMMARIZATION_BLOCK: str = _load("summarization.md")

# Templates (have placeholders -- caller must .format() before use)
MEMORY_BLOCK_TEMPLATE: str = _load("memory_template.md")
IDENTITY_GM_TEMPLATE: str = _load("identity_manager.md")
IDENTITY_CTO_TEMPLATE: str = _load("identity_cto.md")
IDENTITY_ENGINEER_TEMPLATE: str = _load("identity_engineer.md")
