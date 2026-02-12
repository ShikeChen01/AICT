"""
Role-based orchestration rules for sandbox lifecycle.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import InvalidAgentRole
from backend.db.models import Agent
from backend.services.e2b_service import E2BService, SandboxMetadata


def sandbox_should_persist(agent_role: str) -> bool:
    """GM/OM keep persistent sandboxes; engineers are task-ephemeral."""
    if agent_role in ("gm", "om"):
        return True
    if agent_role == "engineer":
        return False
    raise InvalidAgentRole(agent_role)


class OrchestratorService:
    """Coordinates sandbox behavior by role and task lifecycle."""

    def __init__(self, e2b_service: E2BService | None = None):
        self.e2b_service = e2b_service or E2BService()

    async def ensure_sandbox_for_agent(
        self,
        session: AsyncSession,
        agent: Agent,
    ) -> SandboxMetadata:
        if agent.sandbox_id:
            return await self.e2b_service.get_sandbox(session, agent)
        return await self.e2b_service.create_sandbox(
            session=session,
            agent=agent,
            persistent=sandbox_should_persist(agent.role),
        )

    async def close_if_ephemeral(self, session: AsyncSession, agent: Agent) -> None:
        if not sandbox_should_persist(agent.role) and agent.sandbox_id:
            await self.e2b_service.close_sandbox(session, agent)

