"""
ToolContext: runtime context bound to tools for agent execution.

Every tool needs agent_id, project_id, sandbox_id, repo_url, etc.
Context is created once per session and passed to build_tools(agent, project).
Tools never read global state.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ToolContext:
    """Context injected into tools at assembly time."""

    agent_id: UUID
    project_id: UUID
    sandbox_id: str | None
    repo_url: str
    agent_role: str
    agent_display_name: str
    project_name: str
