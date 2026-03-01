"""Shared base types for the universal agent loop tool system.

RunContext, LoopTool, and helper utilities live here so executor modules can
import them without creating circular dependencies with loop_registry.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Repository
from backend.db.repositories.messages import AgentMessageRepository
from backend.services.agent_service import AgentService
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService

MAX_TOOL_RESULT_CHARS = 12000


def truncate_tool_output(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "\n[output truncated]"


def parse_tool_uuid(tool_input: dict, field_name: str, *, required: bool = True) -> UUID | None:
    from backend.tools.result import ToolExecutionError

    raw_value = tool_input.get(field_name)
    if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
        if required:
            raise ToolExecutionError(
                f"'{field_name}' is required and must be a UUID.",
                error_code=ToolExecutionError.INVALID_INPUT,
                hint=f"Provide a valid UUID string for '{field_name}'.",
            )
        return None
    try:
        return UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ToolExecutionError(
            f"Invalid UUID for '{field_name}': {raw_value!r}",
            error_code=ToolExecutionError.INVALID_INPUT,
            hint=f"Use list_agents or list_tasks to find the correct UUID for '{field_name}'.",
        ) from exc


@dataclass
class RunContext:
    """Runtime context injected into every tool executor for a single agent session."""

    db: AsyncSession
    agent: Agent
    project: Repository
    session_id: UUID
    message_service: MessageService
    session_service: SessionService
    task_service: TaskService
    agent_service: AgentService
    agent_msg_repo: AgentMessageRepository
    emit_agent_message: Callable[[object], None] | None = field(default=None)


ToolExecutor = Callable[[RunContext, dict], Awaitable[str | Any]]


@dataclass
class LoopTool:
    """Descriptor for a single loop tool.

    allowed_roles: list of role strings, or ["*"] to grant to all roles.
    execute: None for the special 'end' tool, which the loop handles separately.
    """

    name: str
    description: str
    input_schema: dict
    allowed_roles: list[str]
    execute: ToolExecutor | None = field(default=None)
