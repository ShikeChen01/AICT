"""
Role-based orchestration rules for sandbox lifecycle.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from backend.config import settings
from backend.core.exceptions import InvalidAgentRole
from backend.db.models import Agent
from backend.graph.events import emit_agent_log
from backend.graph.utils import extract_text_content
from backend.graph.workflow import create_graph
from backend.logging.my_logger import get_logger
from backend.services.sandbox_service import SandboxMetadata, SandboxService

logger = get_logger(__name__)

_graph_init_lock = asyncio.Lock()
_graph_app: Any | None = None
_graph_checkpointer_cm: Any | None = None


def _to_postgres_conn_string(database_url: str) -> str:
    """
    Convert SQLAlchemy async URLs to a psycopg-compatible postgres URL.
    """
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if database_url.startswith("postgres+asyncpg://"):
        return database_url.replace("postgres+asyncpg://", "postgresql://", 1)
    return database_url


async def _run_checkpointer_setup(checkpointer: Any) -> None:
    """
    Run checkpointer setup if the backend supports it.
    """
    setup_fn = getattr(checkpointer, "setup", None) or getattr(checkpointer, "asetup", None)
    if setup_fn is None:
        return
    result = setup_fn()
    if inspect.isawaitable(result):
        await result


async def _build_graph_app():
    """
    Build and compile the LangGraph app with configured persistence backend.
    """
    global _graph_checkpointer_cm

    if settings.graph_persist_postgres:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except Exception as exc:  # pragma: no cover - optional dependency path
            logger.warning(
                "Postgres graph persistence requested but unavailable (%s); using MemorySaver.",
                exc,
            )
        else:
            conn_string = _to_postgres_conn_string(settings.database_url)
            cm = None
            try:
                cm = AsyncPostgresSaver.from_conn_string(conn_string)
                checkpointer = await cm.__aenter__()
                await _run_checkpointer_setup(checkpointer)
                _graph_checkpointer_cm = cm
                logger.info("LangGraph checkpointer initialized with PostgresSaver.")
                return create_graph().compile(checkpointer=checkpointer)
            except Exception as exc:  # pragma: no cover - external dependency path
                logger.warning(
                    "Failed to initialize PostgresSaver (%s); using MemorySaver.",
                    exc,
                )
                if cm is not None:
                    try:
                        await cm.__aexit__(None, None, None)
                    except Exception:
                        pass

    return create_graph().compile(checkpointer=MemorySaver())


async def initialize_graph_runtime(force: bool = False):
    """
    Initialize global graph runtime once at startup.
    """
    global _graph_app

    if _graph_app is not None and not force:
        return _graph_app

    async with _graph_init_lock:
        if _graph_app is not None and not force:
            return _graph_app
        _graph_app = await _build_graph_app()
        return _graph_app


async def get_graph_app():
    """
    Return initialized graph runtime, creating it lazily if needed.
    """
    if _graph_app is None:
        await initialize_graph_runtime()
    return _graph_app


async def shutdown_graph_runtime() -> None:
    """
    Close graph persistence resources on app shutdown.
    """
    global _graph_app, _graph_checkpointer_cm

    async with _graph_init_lock:
        _graph_app = None
        if _graph_checkpointer_cm is not None:
            try:
                await _graph_checkpointer_cm.__aexit__(None, None, None)
            finally:
                _graph_checkpointer_cm = None

def sandbox_should_persist(agent_role: str) -> bool:
    """
    Determine sandbox persistence by role.

    Leadership roles (manager, cto) keep persistent sandboxes so their
    context survives across tasks.  Execution roles (engineer, worker,
    researcher, reviewer) get ephemeral sandboxes that are reclaimed when
    the task ends — aligns with the v3 ClusterSpec topology role set.
    """
    _PERSISTENT_ROLES: frozenset[str] = frozenset({"manager", "cto"})
    _EPHEMERAL_ROLES: frozenset[str] = frozenset({"engineer", "worker", "researcher", "reviewer"})
    if agent_role in _PERSISTENT_ROLES:
        return True
    if agent_role in _EPHEMERAL_ROLES:
        return False
    raise InvalidAgentRole(agent_role)


def _persistent_for_agent(agent: Agent) -> bool:
    _ALL_TYPED_ROLES = {"manager", "cto", "engineer", "worker", "researcher", "reviewer"}
    if agent.role in _ALL_TYPED_ROLES:
        return sandbox_should_persist(agent.role)
    return bool(agent.sandbox_persist)


class OrchestratorService:
    """Coordinates sandbox behavior and runs the Agent Graph."""

    def __init__(self, sandbox_service: SandboxService | None = None):
        self.sandbox_service = sandbox_service or SandboxService()

    async def ensure_sandbox_for_agent(
        self,
        session: AsyncSession,
        agent: Agent,
    ) -> SandboxMetadata:
        return await self.sandbox_service.ensure_running_sandbox(
            session=session,
            agent=agent,
            persistent=_persistent_for_agent(agent),
        )

    async def close_if_ephemeral(self, session: AsyncSession, agent: Agent) -> None:
        if not sandbox_should_persist(agent.role) and agent.sandbox_id:
            await self.sandbox_service.close_sandbox(session, agent)

    async def wake_agent(self, session: AsyncSession, agent: Agent) -> SandboxMetadata:
        """
        Wake an agent and ensure sandbox readiness.
        """
        if agent.status == "sleeping":
            agent.status = "active"
        try:
            from backend.workers.message_router import get_message_router

            get_message_router().notify(agent.id)
        except Exception as exc:
            logger.warning(
                "wake_agent: could not notify router for agent %s: %s",
                agent.id,
                exc,
            )
        return await self.ensure_sandbox_for_agent(session, agent)

    async def run_manager_graph(
        self,
        session: AsyncSession,
        manager: Agent,
        user_message: str,
        history_from_db: list | None = None,
    ) -> str:
        """
        Execute the Manager Graph for a turn.
        
        Args:
            session: DB session.
            manager: The Manager agent model.
            user_message: The new message from the user.
            history_from_db: Optional list of previous chat messages to seed the graph state.
        
        Returns:
            The Manager's response text. On error, returns a user-friendly error message
            rather than raising an exception.
        """
        async def _emit_empty_output_diagnostic(
            reason_code: str,
            details: dict[str, Any],
        ) -> None:
            logger.warning(
                "Manager empty output (%s) for project %s | details=%s",
                reason_code,
                manager.project_id,
                details,
            )
            await emit_agent_log(
                project_id=manager.project_id,
                agent_role="manager",
                log_type="error",
                content=f"Manager returned no output ({reason_code}). Details: {str(details)[:200]}",
                agent_id=manager.id,
            )

        try:
            await self.wake_agent(session, manager)
            graph_app = await get_graph_app()
            
            # Build initial state configuration
            config = {"configurable": {"thread_id": str(manager.project_id)}}
            
            # Check if state exists
            current_state = await graph_app.aget_state(config)
            inputs = {}
            
            if not current_state.values and history_from_db:
                # Initialize with history if state is empty
                converted_history = []
                for msg in history_from_db:
                    role = getattr(msg, "role", "user")
                    content = getattr(msg, "content", "")
                    if role == "user":
                        converted_history.append(HumanMessage(content=content))
                    elif role == "manager":
                        converted_history.append(AIMessage(content=content))
                
                # Append the new user message
                inputs["messages"] = converted_history + [HumanMessage(content=user_message)]
            else:
                # Just add the new message
                inputs["messages"] = [HumanMessage(content=user_message)]
                
            inputs["project_id"] = str(manager.project_id)
            inputs["next"] = "manager"
            
            # Invoke the graph
            final_state = await graph_app.ainvoke(inputs, config=config)
            
            # Extract the final response from the Manager
            messages = final_state.get("messages", [])
            tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]
            for tool_msg in tool_messages[-5:]:
                await emit_agent_log(
                    project_id=manager.project_id,
                    agent_id=manager.id,
                    agent_role="manager",
                    log_type="tool_result",
                    content=f"Tool result: {tool_msg.name or 'tool'} — {str(tool_msg.content)[:200]}",
                    tool_name=tool_msg.name,
                )
            if not messages:
                reason_code = "EMPTY_MESSAGES"
                details = {
                    "message_count": 0,
                    "state_keys": list(final_state.keys()),
                }
                await _emit_empty_output_diagnostic(reason_code, details)
                return (
                    "I could not produce a response for this turn.\n\n"
                    "Reason code: EMPTY_MESSAGES\n"
                    "Please retry your request."
                )

            # Prefer the most recent AI message with extractable text.
            ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
            for ai_msg in reversed(ai_messages):
                extracted = extract_text_content(getattr(ai_msg, "content", ""))
                if extracted.strip():
                    return extracted

            # No AI text found; produce diagnostic reason codes.
            last_msg = messages[-1]
            if not ai_messages:
                reason_code = "LAST_MESSAGE_NOT_AI"
                details = {
                    "message_count": len(messages),
                    "last_message_type": type(last_msg).__name__,
                }
                await _emit_empty_output_diagnostic(reason_code, details)
                return (
                    "I could not produce a response for this turn.\n\n"
                    "Reason code: LAST_MESSAGE_NOT_AI\n"
                    "Please retry your request."
                )

            last_ai = ai_messages[-1]
            content = getattr(last_ai, "content", None)
            if isinstance(content, str):
                reason_code = "EMPTY_MANAGER_CONTENT"
                details = {
                    "message_count": len(messages),
                    "last_message_type": type(last_ai).__name__,
                    "content_shape": "str",
                    "tool_call_count": len(getattr(last_ai, "tool_calls", []) or []),
                }
            elif isinstance(content, list):
                reason_code = "UNSUPPORTED_MULTIPART_CONTENT"
                details = {
                    "message_count": len(messages),
                    "last_message_type": type(last_ai).__name__,
                    "content_shape": "list",
                    "list_item_types": [type(part).__name__ for part in content[:5]],
                    "tool_call_count": len(getattr(last_ai, "tool_calls", []) or []),
                }
            else:
                reason_code = "UNSUPPORTED_CONTENT_TYPE"
                details = {
                    "message_count": len(messages),
                    "last_message_type": type(last_ai).__name__,
                    "content_shape": type(content).__name__,
                }

            await _emit_empty_output_diagnostic(reason_code, details)
            return (
                "I could not produce a response for this turn.\n\n"
                f"Reason code: {reason_code}\n"
                "Please retry your request."
            )
            
        except Exception as exc:
            # Log the full error for debugging
            logger.exception("Graph execution failed for project %s: %s", manager.project_id, exc)
            
            # Return a user-friendly error message
            error_type = type(exc).__name__
            error_msg = str(exc)
            
            # Truncate very long error messages
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            
            return (
                f"I encountered an error while processing your request.\n\n"
                f"**Error**: {error_type}: {error_msg}\n\n"
                "Please try again. If the problem persists, check the backend logs for details."
            )

    async def invoke_gm(
        self,
        session: AsyncSession,
        manager: Agent,
        history: list,
        user_message: str,
    ) -> str:
        """Compatibility wrapper for run_manager_graph."""
        return await self.run_manager_graph(session, manager, user_message, history_from_db=history)
