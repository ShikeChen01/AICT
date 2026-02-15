"""
Agent service — manages agent lifecycle and engineer spawning.

- Enforces MAX_ENGINEERS limit when spawning engineers
- Ensures GM and OM exist for new projects
- Coordinates with E2B/orchestrator for sandbox lifecycle
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import MaxEngineersReached, ProjectNotFoundError
from backend.db.models import Agent, Project, VALID_ROLES


class AgentService:
    """Manage agent creation and lifecycle with role-based limits."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_by_role(self, project_id: UUID, role: str) -> int:
        """Count agents with the given role in a project."""
        if role not in VALID_ROLES:
            return 0
        result = await self.session.execute(
            select(func.count(Agent.id)).where(
                Agent.project_id == project_id,
                Agent.role == role,
            )
        )
        return int(result.scalar() or 0)

    async def list_by_role(self, project_id: UUID, role: str) -> list[Agent]:
        """List all agents with the given role in a project."""
        if role not in VALID_ROLES:
            return []
        result = await self.session.execute(
            select(Agent).where(
                Agent.project_id == project_id,
                Agent.role == role,
            ).order_by(Agent.display_name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, agent_id: UUID) -> Agent | None:
        """Get an agent by ID."""
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def spawn_engineer(
        self,
        project_id: UUID,
        *,
        display_name: str | None = None,
        model: str = "claude-4.5",
        module_path: str | None = None,
    ) -> Agent:
        """
        Create a new engineer agent for the project.

        Raises MaxEngineersReached if the project already has max_engineers.
        """
        count = await self.count_by_role(project_id, "engineer")
        limit = settings.max_engineers
        if count >= limit:
            raise MaxEngineersReached(limit)

        # Compute display name (Engineer-1, Engineer-2, ...)
        if display_name is None:
            display_name = f"Engineer-{count + 1}"

        agent = Agent(
            project_id=project_id,
            role="engineer",
            display_name=display_name,
            model=model,
            status="sleeping",
            sandbox_persist=False,
            priority=2,
            current_task_id=None,
        )
        if module_path:
            # Store module_path on agent if needed (could be on Task instead)
            pass  # Agent model doesn't have module_path; tasks do
        self.session.add(agent)
        await self.session.flush()
        await self.session.refresh(agent)
        return agent

    async def ensure_project_agents(
        self,
        project: Project,
        *,
        gm_model: str = "gemini-2.5-pro",
        om_model: str = "claude-4-sonnet",
    ) -> tuple[Agent, Agent]:
        """
        Ensure GM and OM agents exist for a project. Create them if missing.

        Returns (gm, om).
        """
        result = await self.session.execute(
            select(Agent).where(
                Agent.project_id == project.id,
                Agent.role.in_(("gm", "om", "manager")),
            )
        )
        existing = {a.role: a for a in result.scalars().all()}
        # Normalize manager -> gm for lookup
        gm = existing.get("gm") or existing.get("manager")
        om = existing.get("om")

        if not gm:
            gm = Agent(
                project_id=project.id,
                role="gm",
                display_name="GM",
                model=gm_model,
                status="sleeping",
                sandbox_persist=True,
                priority=0,
            )
            self.session.add(gm)
            await self.session.flush()
            await self.session.refresh(gm)

        if not om:
            om = Agent(
                project_id=project.id,
                role="om",
                display_name="OM-1",
                model=om_model,
                status="sleeping",
                sandbox_persist=True,
                priority=1,
            )
            self.session.add(om)
            await self.session.flush()
            await self.session.refresh(om)

        return gm, om

    async def get_or_create_project_agents(
        self,
        project_id: UUID,
    ) -> tuple[Agent, Agent]:
        """
        Get GM and OM for a project, creating them if the project exists but
        has no agents.
        """
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ProjectNotFoundError(project_id)
        return await self.ensure_project_agents(project)


def get_agent_service(session: AsyncSession) -> AgentService:
    """Factory function to create AgentService instance."""
    return AgentService(session)
