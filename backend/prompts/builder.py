"""
Internal helpers for individual prompt blocks.

Each function formats a single block from loaded .md templates.
Orchestration (block ordering, message list management) lives in assembly.py.
"""

from __future__ import annotations

import json

from backend.db.models import Agent
from backend.prompts.loader import (
    IDENTITY_CTO_TEMPLATE,
    IDENTITY_ENGINEER_TEMPLATE,
    IDENTITY_GM_TEMPLATE,
    MEMORY_BLOCK_TEMPLATE,
    TOOL_IO_BASE_BLOCK,
    TOOL_IO_CTO_BLOCK,
    TOOL_IO_ENGINEER_BLOCK,
    TOOL_IO_MANAGER_BLOCK,
)


def get_identity_block(agent: Agent, project_name: str) -> str:
    """Return Identity block for the agent's role.

    For custom roles (not manager/cto/engineer), returns a generic identity
    that uses the agent's display_name and project name.
    """
    if agent.role == "manager":
        return IDENTITY_GM_TEMPLATE.format(project_name=project_name)
    if agent.role == "cto":
        return IDENTITY_CTO_TEMPLATE.format(project_name=project_name)
    if agent.role == "engineer":
        return IDENTITY_ENGINEER_TEMPLATE.format(
            agent_name=agent.display_name,
            project_name=project_name,
        )
    # Custom roles: use a generic identity block
    return (
        f"You are **{agent.display_name}**, a specialized agent on project \"{project_name}\".\n\n"
        f"Your role is: {agent.role}. Follow your prompt instructions and use your available tools to complete tasks."
    )


def get_memory_block(memory_content: str | dict | None) -> str:
    """Return Memory block. memory_content is agent.memory (JSON string/dict or None)."""
    if memory_content is None:
        text = "No memory recorded yet."
    elif isinstance(memory_content, dict):
        text = json.dumps(memory_content, indent=2).strip() or "No memory recorded yet."
    elif isinstance(memory_content, str) and memory_content.strip():
        text = memory_content.strip()
    else:
        text = "No memory recorded yet."
    return MEMORY_BLOCK_TEMPLATE.format(memory_content=text)


def get_tool_io_block(role: str) -> str:
    """Return tool input/output contract for the agent role.

    Custom roles get the base tool I/O block plus the engineer-specific
    block (most permissive) as a reasonable default.
    """
    if role == "manager":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_MANAGER_BLOCK
    if role == "cto":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_CTO_BLOCK
    if role == "engineer":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_ENGINEER_BLOCK
    # Custom roles: use engineer (worker) tool I/O as default — most permissive
    return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_ENGINEER_BLOCK
