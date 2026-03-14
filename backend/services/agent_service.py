"""
Agent service — manages agent lifecycle with template-driven blank-canvas design.

Phase 2 (v3.1 refactoring):
- Removes hardcoded role-based agent creation (no forced Manager+CTO)
- Agents are created from templates; role_label is purely cosmetic (stored in Agent.role)
- Agents created from ProjectDefaults.default_template_id for new projects
- No role-based limits (engineer limits, role-protected deletion) — all agents are equals
- Service layer provides generic create_agent() and seed_default_agent() methods

Backward compatibility:
- ensure_project_agents() and spawn_engineer() are DEPRECATED but still functional
- They delegate to new methods for compatibility during migration
"""

from __future__ import annotations

import uuid as _uuid
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import ProjectNotFoundError
from backend.db.models import Agent, AgentTemplate, ProjectDefaults, Repository, Task
from backend.db.repositories.agent_templates import AgentTemplateRepository, PromptBlockConfigRepository
from backend.db.repositories.tool_configs import ToolConfigRepository
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.llm.model_resolver import default_model_for_role, infer_provider




class AgentService:
    """Manage agent creation and lifecycle — template-driven, role-agnostic.

    All agents are created from templates as blank canvases. The role_label
    (Agent.role) is purely cosmetic and user-facing; no role-based limits or
    privilege enforcement applies.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_role(self, project_id: UUID, role: str) -> list[Agent]:
        """Convenience filter: list all agents with the given role_label in a project.

        This is NOT enforced by the system; it's a simple query convenience for UI.
        """
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
        role_label: str,
        display_name: str,
        template: AgentTemplate,
    ) -> Agent:
        """Internal: Create an agent from a template.

        Copies model/provider/thinking_enabled from template to agent snapshot.
        Copies prompt block configs from template to agent level.
        Seeds tool configs for the agent based on template's base_role.

        Args:
            project_id: Project ID
            role_label: Cosmetic role label (stored in Agent.role) — purely user-facing
            display_name: Human-readable agent name
            template: The AgentTemplate to create from

        Returns:
            Created Agent instance
        """
        agent = Agent(
            id=_uuid.uuid4(),
            project_id=project_id,
            template_id=template.id,
            role=role_label,
            display_name=display_name,
            tier=None,  # deprecated; template.name differentiates agent types
            model=template.model,
            provider=template.provider or infer_provider(template.model),
            thinking_enabled=template.thinking_enabled,
            status="sleeping",
            current_task_id=None,
        )
        self.session.add(agent)
        await self.session.flush()
        await self.session.refresh(agent)

        # Copy template block rows to agent-level block rows
        block_repo = PromptBlockConfigRepository(self.session)
        await block_repo.copy_template_blocks_to_agent(template.id, agent.id)

        # Seed tool configs for this agent from tool_descriptions.json
        # Use template's base_role for tool seeding (not affected by role_label)
        base_role = getattr(template, "base_role", None) or "worker"
        tool_repo = ToolConfigRepository(self.session)
        await tool_repo.seed_for_agent(agent.id, base_role)

        return agent

    async def create_agent(
        self,
        project_id: UUID,
        template_id: UUID,
        *,
        display_name: str | None = None,
        role_label: str | None = None,
    ) -> Agent:
        """Create any agent from a template.

        Generic agent creation with no role-based limits or special logic.
        The role_label is purely cosmetic (stored in Agent.role as user-facing label).

        Args:
            project_id: Project ID
            template_id: Template to create from
            display_name: Human-readable agent name (defaults to template.name)
            role_label: Cosmetic role label for display (defaults to template.base_role)

        Returns:
            Created Agent instance

        Raises:
            ValueError: If template not found or does not belong to project
        """
        result = await self.session.execute(
            select(AgentTemplate).where(AgentTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Agent template {template_id} not found.")
        if template.project_id != project_id:
            raise ValueError("Template does not belong to this project.")

        if display_name is None:
            display_name = template.name or f"Agent-{template.base_role}"
        if role_label is None:
            role_label = template.base_role or "worker"

        agent = await self._create_agent_from_template(
            project_id, role_label, display_name, template
        )
        return agent

    async def seed_default_agent(self, project: Repository) -> Agent:
        """Create ONE default agent for a new project.

        Uses ProjectDefaults.default_template_id if configured; falls back to
        the system default template for the project.

        Args:
            project: Project instance

        Returns:
            Created default Agent instance
        """
        # Try to get project-specific default template
        result = await self.session.execute(
            select(ProjectDefaults).where(ProjectDefaults.project_id == project.id)
        )
        proj_defaults = result.scalar_one_or_none()
        template_id = proj_defaults.default_template_id if proj_defaults else None

        if template_id:
            result = await self.session.execute(
                select(AgentTemplate).where(AgentTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
        else:
            # Fall back to system default template
            template_repo = AgentTemplateRepository(self.session)
            templates = await template_repo.ensure_system_defaults(project.id)
            template = templates.get("worker")  # Generic system default

        if not template:
            raise ValueError(f"No default template available for project {project.id}")

        agent = await self._create_agent_from_template(
            project.id,
            role_label="worker",  # Default cosmetic label
            display_name="Default Agent",
            template=template,
        )
        return agent

    # ── DEPRECATED: Role-based agent creation (Phase 1 compat) ──────────────

    async def ensure_project_agents(
        self,
        project: Repository,
        *,
        manager_model: str | None = None,
        cto_model: str | None = None,
    ) -> tuple[Agent, Agent]:
        """DEPRECATED: Ensure manager and CTO agents exist for a project.

        This method enforces the old Phase 1 behavior: creating and protecting
        Manager + CTO roles. In Phase 2+, use seed_default_agent() instead.

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
                project.id, "manager", "GM", mgr_template
            )

        if not cto:
            cto_template = templates["cto"]
            if cto_model:
                cto_template.model = cto_model
                cto_template.provider = infer_provider(cto_model)
            cto = await self._create_agent_from_template(
                project.id, "cto", "CTO", cto_template
            )

        return manager, cto

    async def spawn_engineer(
        self,
        project_id: UUID,
        *,
        display_name: str | None = None,
        template_id: UUID | None = None,
        seniority: str | None = None,
        module_path: str | None = None,
    ) -> Agent:
        """DEPRECATED: Create a new engineer agent with max_engineers limit.

        In Phase 1, this enforced engineer limits and used role-based templates.
        Phase 2 removes these constraints; use create_agent() instead.

        For backward compatibility, this still works but ignores limits.
        seniority and module_path are accepted but ignored.
        """
        # Phase 1 behavior: count engineers and check limit
        # Phase 2: We ignore the limit but kept the counting logic for reference
        # count = await self.count_by_role(project_id, "engineer")
        # In Phase 2+, we skip the limit check entirely

        if display_name is None:
            # Generate a default name (old behavior)
            result = await self.session.execute(
                select(func.count(Agent.id)).where(
                    Agent.project_id == project_id,
                    Agent.role == "engineer",
                )
            )
            count = int(result.scalar() or 0)
            display_name = f"Engineer-{count + 1}"

        template_repo = AgentTemplateRepository(self.session)

        if template_id:
            result = await self.session.execute(
                select(AgentTemplate).where(AgentTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
        else:
            template = await template_repo.get_by_project_and_role(project_id, "worker")

        if template:
            agent = await self._create_agent_from_template(
                project_id, "engineer", display_name, template
            )
            return agent
        else:
            # Fallback: create template-less agent (shouldn't happen in Phase 2+)
            agent = Agent(
                id=_uuid.uuid4(),
                project_id=project_id,
                role="engineer",
                display_name=display_name,
                model=default_model_for_role("engineer"),
                provider=infer_provider(default_model_for_role("engineer")),
                thinking_enabled=False,
                status="sleeping",
                current_task_id=None,
            )
            self.session.add(agent)
            await self.session.flush()
            await self.session.refresh(agent)
            return agent

    async def spawn_from_template(
        self,
        project_id: UUID,
        template_id: UUID,
        *,
        display_name: str | None = None,
    ) -> Agent:
        """Create a new agent from any agent template.

        This is the template-driven agent creation path (Phase 2+).
        The agent's role_label is derived from template.base_role.

        Args:
            project_id: Project ID
            template_id: Template to create from
            display_name: Human-readable name (defaults to template.name)

        Returns:
            Created Agent instance
        """
        result = await self.session.execute(
            select(AgentTemplate).where(AgentTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Agent template {template_id} not found.")
        if template.project_id != project_id:
            raise ValueError("Template does not belong to this project.")

        # Determine the agent role_label from the template's base_role
        base_role = template.base_role or "worker"
        role_map = {"manager": "manager", "cto": "cto", "worker": "engineer"}
        role_label = role_map.get(base_role, base_role)  # custom base_roles use themselves

        if display_name is None:
            display_name = template.name or f"Agent-{base_role}"

        agent = await self._create_agent_from_template(
            project_id, role_label, display_name, template,
        )
        return agent

    async def remove_agent(self, agent_id: UUID, project_id: UUID) -> Agent:
        """Remove an agent from the project.

        In Phase 2+, any agent can be removed (no role-based protection).
        Tasks assigned to the removed agent are reset to backlog.

        Args:
            agent_id: Agent to remove
            project_id: Project ID (for authorization check)

        Returns:
            Removed Agent instance

        Raises:
            ValueError: If agent not found or does not belong to project
        """
        result = await self.session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()

        if agent is None:
            raise ValueError(f"Agent {agent_id} not found.")
        if agent.project_id != project_id:
            raise ValueError("Cannot remove an agent from a different project.")

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
        """DEPRECATED: Get or create manager and CTO for a project.

        Phase 1 behavior kept for backward compatibility.
        Use seed_default_agent() for Phase 2+ workflows.
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
