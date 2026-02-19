"""
Agent service — manages agent lifecycle and engineer spawning.

- Enforces MAX_ENGINEERS limit when spawning engineers
- Ensures Manager and CTO exist for new projects
- Coordinates with E2B/orchestrator for sandbox lifecycle
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import MaxEngineersReached, ProjectNotFoundError
from backend.db.models import Agent, Repository, VALID_ROLES
from backend.llm.model_resolver import normalize_tier, resolve_model


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
        model: str | None = None,
        tier: str | None = None,
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
        normalized_tier = normalize_tier(tier)
        effective_model = resolve_model("engineer", tier=normalized_tier, model_override=model)

        agent = Agent(
            project_id=project_id,
            role="engineer",
            display_name=display_name,
            tier=normalized_tier,
            model=effective_model,
            status="sleeping",
            sandbox_persist=False,
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
        project: Repository,
        *,
        manager_model: str | None = None,
        cto_model: str | None = None,
    ) -> tuple[Agent, Agent]:
        """
        Ensure manager and CTO agents exist for a project. Create them if missing.

        Returns (manager, cto).
        """
        result = await self.session.execute(
            select(Agent).where(
                Agent.project_id == project.id,
                Agent.role.in_(("manager", "cto")),
            )
        )
        existing = {a.role: a for a in result.scalars().all()}
        manager = existing.get("manager")
        cto = existing.get("cto")
        manager_model_resolved = resolve_model("manager", model_override=manager_model)
        cto_model_resolved = resolve_model("cto", model_override=cto_model)

        if not manager:
            manager = Agent(
                project_id=project.id,
                role="manager",
                display_name="GM",
                model=manager_model_resolved,
                status="sleeping",
                sandbox_persist=True,
            )
            self.session.add(manager)
            await self.session.flush()
            await self.session.refresh(manager)

        if not cto:
            cto = Agent(
                project_id=project.id,
                role="cto",
                display_name="CTO",
                model=cto_model_resolved,
                status="sleeping",
                sandbox_persist=True,
            )
            self.session.add(cto)
            await self.session.flush()
            await self.session.refresh(cto)

        return manager, cto

    async def get_or_create_project_agents(
        self,
        project_id: UUID,
    ) -> tuple[Agent, Agent]:
        """
        Get manager and CTO for a project, creating them if the project exists but
        has no agents.
        """
        result = await self.session.execute(
            select(Repository).where(Repository.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ProjectNotFoundError(project_id)
        return await self.ensure_project_agents(project)


def get_agent_service(session: AsyncSession) -> AgentService:
    """Factory function to create AgentService instance."""
    return AgentService(session)
