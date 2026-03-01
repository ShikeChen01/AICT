"""
Prompt block file loader — seed data only.

The .md files in blocks/ are the canonical defaults used to:
1. Seed prompt_block_configs rows at template/agent creation (migration 015, agent_templates.py repo)
2. Reset individual blocks to default via the prompt blocks API

These files are NOT read at LLM call time. The DB (prompt_block_configs table) is the
runtime source of truth. Changes to .md files only take effect when blocks are reseeded
or when a user clicks "Reset to Default" in the UI.
"""

from __future__ import annotations

from pathlib import Path

_BLOCKS_DIR = Path(__file__).parent / "blocks"


def load_block_file(filename: str) -> str:
    """Load a single .md block file. Returns empty string if not found."""
    path = _BLOCKS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def get_all_default_files() -> dict[str, str]:
    """Return all .md files in the blocks/ directory as {filename: content}.

    Used by the prompt blocks API to list available defaults.
    """
    result = {}
    for path in sorted(_BLOCKS_DIR.glob("*.md")):
        result[path.name] = path.read_text(encoding="utf-8")
    return result


# ── Legacy constants — kept for any remaining imports ────────────────────────
# These are NOT used by PromptAssembly. They exist only so code that hasn't
# been migrated yet doesn't break. Remove after full migration.

def _load(filename: str) -> str:
    return load_block_file(filename)


RULES_BLOCK: str = _load("rules.md")
HISTORY_RULES_BLOCK: str = _load("history_rules.md")
INCOMING_MESSAGE_RULES_BLOCK: str = _load("incoming_message_rules.md")
TOOL_RESULT_RULES_BLOCK: str = _load("tool_result_rules.md")
TOOL_IO_BASE_BLOCK: str = _load("tool_io_base.md")
TOOL_IO_MANAGER_BLOCK: str = _load("tool_io_manager.md")
TOOL_IO_CTO_BLOCK: str = _load("tool_io_cto.md")
TOOL_IO_ENGINEER_BLOCK: str = _load("tool_io_engineer.md")
THINKING_BLOCK: str = _load("thinking.md")
MEMORY_BLOCK_TEMPLATE: str = _load("memory_template.md")
IDENTITY_GM_TEMPLATE: str = _load("identity_manager.md")
IDENTITY_CTO_TEMPLATE: str = _load("identity_cto.md")
IDENTITY_ENGINEER_TEMPLATE: str = _load("identity_engineer.md")
LOOPBACK_BLOCK: str = _load("loopback.md")
END_SOLO_WARNING_BLOCK: str = _load("end_solo_warning.md")
SUMMARIZATION_BLOCK: str = _load("summarization.md")
