"""
Sandbox and agent orchestration service for Phase 2+3 v3.1 refactoring.

Handles sandbox lifecycle management and agent activation.
LangGraph workflow has been removed; sandbox persistence is now
controlled via SandboxConfig.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Sandbox
from backend.logging.my_logger import get_logger
from backend.services.sandbox_service import SandboxService

logger = get_logger(__name__)


def shutdown_graph_runtime() -> None:
    """
    DEPRECATED: No-op for backward compatibility.

    Sandbox lifecycle is now user-controlled via SandboxConfig.
    This function is retained for startup/shutdown hooks that may call it.
    """
    pass


class OrchestratorService:
    """
    Manages sandbox orchestration and agent activation.

    In v3.1 Phase 2+3:
    - Sandbox persistence is controlled by SandboxConfig, not agent role.
    - LangGraph workflow has been removed entirely.
    - This service handles the simplified sandbox lifecycle and agent wake-up.
    """

    def __init__(self, sandbox_service: SandboxService | None = None):
        """
        Initialize the orchestrator service.

        Args:
            sandbox_service: Optional custom SandboxService instance.
        """
        self.sandbox_service = sandbox_service or SandboxService()

    async def ensure_sandbox_for_agent(
        self,
        session: AsyncSession,
        agent: Agent,
    ) -> Sandbox:
        """Acquire a headless sandbox for an agent (v4.1).

        Uses the clean acquire_sandbox_for_agent path which checks for
        an existing assignment first, then provisions a new headless
        sandbox if needed.

        Args:
            session: SQLAlchemy async session.
            agent: The agent model.

        Returns:
            The assigned Sandbox model instance.
        """
        return await self.sandbox_service.acquire_sandbox_for_agent(
            session, agent
        )

    async def close_if_ephemeral(self, session: AsyncSession, agent: Agent) -> None:
        """
        DEPRECATED: No-op.

        Sandbox lifecycle is now user-controlled. Sandboxes are not automatically
        closed based on agent role anymore.

        Args:
            session: SQLAlchemy async session.
            agent: The agent model.
        """
        pass

    async def wake_agent(self, session: AsyncSession, agent: Agent) -> Sandbox:
        """Activate a sleeping agent and ensure sandbox readiness.

        Sets agent status to "active" and notifies the message router.

        Args:
            session: SQLAlchemy async session.
            agent: The agent model.

        Returns:
            The assigned Sandbox model instance.
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
