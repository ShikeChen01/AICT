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


# ── Static rule / guidance blocks ───────────────────────────────────────────
RULES_BLOCK: str = _load("rules.md")
HISTORY_RULES_BLOCK: str = _load("history_rules.md")
INCOMING_MESSAGE_RULES_BLOCK: str = _load("incoming_message_rules.md")
TOOL_RESULT_RULES_BLOCK: str = _load("tool_result_rules.md")
TOOL_IO_BASE_BLOCK: str = _load("tool_io_base.md")
TOOL_IO_MANAGER_BLOCK: str = _load("tool_io_manager.md")
TOOL_IO_CTO_BLOCK: str = _load("tool_io_cto.md")
TOOL_IO_ENGINEER_BLOCK: str = _load("tool_io_engineer.md")

# ── Reasoning / identity blocks ──────────────────────────────────────────────
THINKING_BLOCK: str = _load("thinking.md")

# Templates (have placeholders — caller must .format() before use)
MEMORY_BLOCK_TEMPLATE: str = _load("memory_template.md")
IDENTITY_GM_TEMPLATE: str = _load("identity_manager.md")
IDENTITY_CTO_TEMPLATE: str = _load("identity_cto.md")
IDENTITY_ENGINEER_TEMPLATE: str = _load("identity_engineer.md")

# ── Conditional / injected blocks ────────────────────────────────────────────
LOOPBACK_BLOCK: str = _load("loopback.md")
END_SOLO_WARNING_BLOCK: str = _load("end_solo_warning.md")
SUMMARIZATION_BLOCK: str = _load("summarization.md")
