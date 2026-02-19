"""
Event emission helpers for LangGraph nodes.

Provides async-safe methods to broadcast workflow and activity events
from within graph node execution.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


def _get_ws_manager():
    """Lazy import to avoid circular dependencies."""
    from backend.websocket.manager import ws_manager
    return ws_manager


async def emit_workflow_update(
    project_id: str | UUID,
    current_node: str,
    node_status: str,  # "started" or "completed"
    previous_node: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Emit a workflow update event for the live graph visualization.
    
    Args:
        project_id: The project UUID (also used as thread_id).
        current_node: Name of the current node (e.g., "manager", "cto", "engineer").
        node_status: Either "started" or "completed".
        previous_node: Optional name of the previous node.
        metadata: Optional additional metadata.
    """
    try:
        ws_manager = _get_ws_manager()
        await ws_manager.broadcast_workflow_update(
            project_id=UUID(str(project_id)) if isinstance(project_id, str) else project_id,
            thread_id=str(project_id),
            current_node=current_node,
            node_status=node_status,
            previous_node=previous_node,
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Failed to emit workflow_update: %s", exc)


async def emit_agent_log(
    project_id: str | UUID,
    agent_role: str,
    log_type: str,  # "thought", "tool_call", "tool_result", "message"
    content: str,
    agent_id: str | UUID | None = None,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
    tool_output: str | None = None,
) -> None:
    """
    Emit an agent activity log event for the activity feed.
    
    Args:
        project_id: The project UUID.
        agent_role: Role of the agent (e.g., "manager", "cto", "engineer").
        log_type: Type of log entry.
        content: Human-readable description of the activity.
        agent_id: Optional agent UUID (generates a placeholder if not provided).
        tool_name: Name of the tool being called (for tool_call/tool_result).
        tool_input: Tool input arguments.
        tool_output: Tool output/result.
    """
    try:
        ws_manager = _get_ws_manager()
        # Generate a placeholder agent_id if not provided
        from uuid import uuid4
        aid = UUID(str(agent_id)) if agent_id else uuid4()
        pid = UUID(str(project_id)) if isinstance(project_id, str) else project_id
        
        await ws_manager.broadcast_agent_log(
            project_id=pid,
            agent_id=aid,
            agent_role=agent_role,
            log_type=log_type,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
    except Exception as exc:
        logger.warning("Failed to emit agent_log: %s", exc)


async def emit_sandbox_log(
    project_id: str | UUID,
    agent_id: str | UUID,
    sandbox_id: str,
    stream: str,  # "stdout" or "stderr"
    content: str,
) -> None:
    """
    Emit sandbox terminal output for the activity feed.
    
    Args:
        project_id: The project UUID.
        agent_id: The agent UUID.
        sandbox_id: The E2B sandbox ID.
        stream: Either "stdout" or "stderr".
        content: The terminal output content.
    """
    try:
        ws_manager = _get_ws_manager()
        pid = UUID(str(project_id)) if isinstance(project_id, str) else project_id
        aid = UUID(str(agent_id)) if isinstance(agent_id, str) else agent_id
        
        await ws_manager.broadcast_sandbox_log(
            project_id=pid,
            agent_id=aid,
            sandbox_id=sandbox_id,
            stream=stream,
            content=content,
        )
    except Exception as exc:
        logger.warning("Failed to emit sandbox_log: %s", exc)
