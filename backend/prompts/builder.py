"""
Prompt block assembly for the universal agent loop.

Assembles system prompt from Identity, Rules, Thinking, Memory blocks per docs/backend/agents.md.
Token budgets and truncation apply to conversation only; blocks are never truncated.
"""

from __future__ import annotations

import json

from backend.db.models import Agent, Repository
from backend.prompts.loader import (
    IDENTITY_CTO_TEMPLATE,
    IDENTITY_ENGINEER_TEMPLATE,
    IDENTITY_GM_TEMPLATE,
    LOOPBACK_BLOCK,
    MEMORY_BLOCK_TEMPLATE,
    RULES_BLOCK,
    SUMMARIZATION_BLOCK,
    THINKING_BLOCK,
    TOOL_IO_BASE_BLOCK,
    TOOL_IO_CTO_BLOCK,
    TOOL_IO_ENGINEER_BLOCK,
    TOOL_IO_MANAGER_BLOCK,
)


def get_identity_block(agent: Agent, project_name: str) -> str:
    """Return Identity block for the agent's role."""
    if agent.role == "manager":
        return IDENTITY_GM_TEMPLATE.format(project_name=project_name)
    if agent.role == "cto":
        return IDENTITY_CTO_TEMPLATE.format(project_name=project_name)
    if agent.role == "engineer":
        return IDENTITY_ENGINEER_TEMPLATE.format(
            agent_name=agent.display_name,
            project_name=project_name,
        )
    return f"You are {agent.display_name} on project \"{project_name}\"."


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
    """Return tool input/output contract for the agent role."""
    if role == "manager":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_MANAGER_BLOCK
    if role == "cto":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_CTO_BLOCK
    if role == "engineer":
        return TOOL_IO_BASE_BLOCK + "\n" + TOOL_IO_ENGINEER_BLOCK
    return TOOL_IO_BASE_BLOCK


def build_system_prompt(agent: Agent, project: Repository, memory_content: str | None) -> str:
    """
    Build the full system prompt: Identity + Rules + Thinking + Memory.
    Conversation and tool results are injected by the loop as user/assistant/tool messages.
    """
    project_name = project.name or "Project"
    identity = get_identity_block(agent, project_name)
    tool_io = get_tool_io_block(agent.role)
    memory = get_memory_block(memory_content)
    return f"{identity}\n\n{RULES_BLOCK}\n\n{THINKING_BLOCK}\n\n{tool_io}\n\n{memory}"


def get_loopback_block() -> str:
    """Return Loopback block (injected when agent responds without tool calls)."""
    return LOOPBACK_BLOCK


def get_summarization_block() -> str:
    """Return Summarization block (injected at ~70% context capacity)."""
    return SUMMARIZATION_BLOCK
