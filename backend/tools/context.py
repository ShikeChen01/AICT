"""Lightweight, serialisable tool context.

Carries the minimal per-agent metadata needed by tool executors without
requiring live DB sessions or service instances.  Used primarily in unit
tests and in contexts where the full RunContext (which embeds SQLAlchemy
sessions) is not appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class ToolContext:
    """Immutable snapshot of agent/project metadata for a single tool call."""

    agent_id: UUID
    project_id: UUID
    sandbox_id: Optional[str]
    repo_url: str
    agent_role: str
    agent_display_name: str
    project_name: str
