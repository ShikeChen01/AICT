"""
Agent service — manages agent lifecycle and engineer spawning.

- Enforces MAX_ENGINEERS limit when spawning engineers
- Ensures Manager and CTO exist for new projects
- Coordinates with E2B/orchestrator for sandbox lifecycle
- Uses the template system: agents are created from AgentTemplates (write-through)
"""

from __future__ import annotations

import uuid as _uuid
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import MaxEngineersReached, ProjectNotFoundError
from backend.db.models import Agent, AgentTemplate, Repository, Task, VALID_ROLES
from backend.db.repositories.agent_templates import AgentTemplateRepository, PromptBlockConfigRepository
from backend.db.repositories.tool_configs import ToolConfigRepository
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.llm.model_resolver import default_model_for_role, infer_provider

_ROLE_TO_BASE_ROLE = {"manager": "manager", "cto": "cto", "engineer": "worker"}


def _model_for_tier(tier: str) -> str:
    """Return the config model for a given engineer tier."""
    if tier == "senior":
        return settings.engineer_senior_model
    if tier == "intermediate":
        return settings.engineer_intermediate_model
    return settings.engineer_junior_model


class AgentService:
    """Manage agent creation and lifecycle with role-based limits."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_by_role(self, project_id: UUID, role: str) -> int:
        """Count agents with the given role in a project."""
        result = await self.session.execute(
            select(func.count(Agent.id)).where(
                Agent.project_id == project_id,
                Agent.role == role,
            )
        )
        return int(result.scalar() or 0)

    async def list_by_role(self, project_id: UUID, role: str) -> list[Agent]:
        """List all agents with the given role in a project."""
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

    async def _create_agent_from_template(
        self,
        project_id: UUID,
        role: str,
        display_name: str,
        template: AgentTemplate,
    ) -> Agent:
        """Create an agent, copying model/provider/thinking_enabled from template.

        Also copies prompt block configs from template to agent level.
        Sandbox persistence is now determined by agent role.
        """
        agent = Agent(
            id=_uuid.uuid4(),
            project_id=project_id,
            template_id=template.id,
            role=role,
            display_name=display_name,
            tier=None,  # deprecated; template.name differentiates agent types
            model=template.model,
            provider=template.provider or infer_provider(template.model),
            thinking_enabled=template.thinking_enabled,
            status="sleeping",
            # Note: sandbox_persist is now determined by role; the parameter is deprecated
            current_task_id=None,
        )
        self.session.add(agent)
        await self.session.flush()
        await self.session.refresh(agent)

        # Copy template block rows to agent-level block rows
        block_repo = PromptBlockConfigRepository(self.session)
        await block_repo.copy_template_blocks_to_agent(template.id, agent.id)

        # Seed tool configs for this agent from tool_descriptions.json
        # Use template's base_role if available, otherwise fall back to role mapping
        base_role = getattr(template, "base_role", None) or _ROLE_TO_BASE_ROLE.get(role, "worker")
        tool_repo = ToolConfigRepository(self.session)
        await tool_repo.seed_for_agent(agent.id, base_role)

        return agent

    async def spawn_engineer(
        self,
        project_id: UUID,
        *,
        display_name: str | None = None,
        template_id: UUID | None = None,
        seniority: str | None = None,
        module_path: str | None = None,
    ) -> Agent:
        """Create a new engineer agent for the project.

        If template_id is provided, uses that template's model/provider/thinking.
        Otherwise uses the project's default Engineer template (system default).
        Raises MaxEngineersReached if the project already has max_engineers.
        """
        count = await self.count_by_role(project_id, "engineer")
        ps_repo = ProjectSettingsRepository(self.session)
        project_settings = await ps_repo.get_by_project(project_id)
        limit = (
            project_settings.max_engineers
            if project_settings is not None
            else settings.max_engineers
        )
        if count >= limit:
            raise MaxEngineersReached(limit)

        if display_name is None:
            display_name = f"Engineer-{count + 1}"

        template_repo = AgentTemplateRepository(self.session)

        if template_id:
            result = await self.session.execute(
                select(AgentTemplate).where(AgentTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
        else:
            template = await template_repo.get_by_project_and_role(project_id, "worker")

        # Normalize seniority for model selection and tier storage
        from backend.llm.model_resolver import normalize_seniority
        normalized_tier = normalize_seniority(seniority) if seniority else "junior"

        if template:
            agent = await self._create_agent_from_template(
                project_id, "engineer", display_name, template
            )
            # Override model with seniority-specific default if seniority was explicitly provided
            if seniority:
                seniority_model = _model_for_tier(normalized_tier)
                agent.model = seniority_model
                agent.provider = infer_provider(seniority_model)
                agent.tier = normalized_tier
                await self.session.flush()
            return agent
        else:
            # Fallback: create template-less agent with seniority-aware defaults
            seniority_model = _model_for_tier(normalized_tier)
            agent = Agent(
                id=_uuid.uuid4(),
                project_id=project_id,
                role="engineer",
                display_name=display_name,
                model=seniority_model,
                provider=infer_provider(seniority_model),
                tier=normalized_tier,
                thinking_enabled=False,
                status="sleeping",
                sandbox_persist=False,
                current_task_id=None,
            )
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
        """Ensure manager and CTO agents exist for a project. Create them if missing.

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

        # Ensure system default templates exist
        template_repo = AgentTemplateRepository(self.session)
        templates = await template_repo.ensure_system_defaults(project.id)

        if not manager:
            mgr_template = templates["manager"]
            if manager_model:
                mgr_template.model = manager_model
                mgr_template.provider = infer_provider(manager_model)
            manager = await self._create_agent_from_template(
                project.id, "manager", "GM", mgr_template, sandbox_persist=True
            )

        if not cto:
            cto_template = templates["cto"]
            if cto_model:
                cto_template.model = cto_model
                cto_template.provider = infer_provider(cto_model)
            cto = await self._create_agent_from_template(
                project.id, "cto", "CTO", cto_template, sandbox_persist=True
            )

        return manager, cto

    async def spawn_from_template(
        self,
        project_id: UUID,
        template_id: UUID,
        *,
        display_name: str | None = None,
        sandbox_persist: bool = False,  # Deprecated; sandbox persistence is now determined by role
    ) -> Agent:
        """Create a new agent from any agent template (design).

        Unlike spawn_engineer, this method works with any role/base_role
        and does not enforce engineer-specific limits. The template defines
        the agent's role, model, provider, thinking config, and prompt blocks.
        """
        result = await self.session.execute(
            select(AgentTemplate).where(AgentTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Agent template {template_id} not found.")
        if template.project_id != project_id:
            raise ValueError("Template does not belong to this project.")

        # Determine the agent role from the template's base_role
        base_role = template.base_role or "worker"
        role_map = {"manager": "manager", "cto": "cto", "worker": "engineer"}
        role = role_map.get(base_role, base_role)  # custom base_roles use themselves as role

        if display_name is None:
            display_name = template.name or f"Agent-{base_role}"

        agent = await self._create_agent_from_template(
            project_id, role, display_name, template,
        )
        return agent

    async def remove_agent(self, agent_id: UUID, caller_project_id: UUID) -> Agent:
        """Permanently remove an agent from the project (manager and CTO are protected)."""
        result = await self.session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise ValueError(f"Agent {agent_id} not found.")
        if agent.project_id != caller_project_id:
            raise ValueError("Cannot remove an agent from a different project.")
        if agent.role in ("manager", "cto"):
            raise ValueError(f"Cannot remove a {agent.role} — only non-core agents can be removed.")

        # Reset tasks assigned to this agent that are still actionable
        await self.session.execute(
            update(Task)
            .where(
                Task.assigned_agent_id == agent_id,
                Task.status.in_(("todo", "in_progress")),
            )
            .values(assigned_agent_id=None, status="backlog")
        )

        # Break circular FK before deletion
        agent.current_task_id = None
        await self.session.flush()

        await self.session.delete(agent)
        return agent

    async def get_or_create_project_agents(
        self,
        project_id: UUID,
    ) -> tuple[Agent, Agent]:
        """Get manager and CTO for a project, creating them if the project exists but has no agents."""
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
