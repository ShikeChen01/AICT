"""
E2B sandbox lifecycle service.

Uses the E2B SDK when configured; falls back to local metadata IDs for
development and tests.

Sandboxes are initialized with project repo cloned for engineers.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import SandboxNotFoundError
from backend.db.models import Agent, Repository

try:
    from e2b import AsyncSandbox
except Exception:  # pragma: no cover - optional dependency in local tests
    AsyncSandbox = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxMetadata:
    sandbox_id: str
    agent_id: str
    persistent: bool
    status: str


class E2BService:
    """Manage sandbox lifecycle and agent sandbox references."""

    @staticmethod
    def _should_use_real_provider() -> bool:
        return bool(settings.e2b_api_key and AsyncSandbox is not None)

    @staticmethod
    def _is_local_fallback_sandbox(sandbox_id: str) -> bool:
        return sandbox_id.startswith("local-sbox-")

    @staticmethod
    def _apply_sdk_api_key() -> None:
        # SDK reads from env var.
        os.environ["E2B_API_KEY"] = settings.e2b_api_key

    async def _get_project(self, session: AsyncSession, project_id) -> Optional[Repository]:
        """Get repository by ID for sandbox initialization."""
        result = await session.execute(
            select(Repository)
            .options(selectinload(Repository.owner))
            .where(Repository.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _initialize_sandbox(
        self,
        sandbox,
        agent: Agent,
        project: Optional[Repository],
    ) -> None:
        """
        Initialize sandbox with project setup.
        
        For engineers: Clone the code repo and set up working directory.
        For managers: Set up access to spec files.
        """
        if not sandbox or not project:
            return

        try:
            # Create working directory
            await sandbox.filesystem.make_dir("/home/user/project")

            if agent.role == "engineer" and project.code_repo_url:
                # Clone code repo for engineers
                clone_cmd = f"git clone {project.code_repo_url} /home/user/project"
                owner_github_token = project.owner.github_token if project.owner else None
                if owner_github_token:
                    # Use the repository owner's token for private repos.
                    repo_url = project.code_repo_url.replace(
                        "https://", f"https://{owner_github_token}@"
                    )
                    clone_cmd = f"git clone {repo_url} /home/user/project"

                proc = await sandbox.process.start(clone_cmd)
                await proc.wait()

                if proc.exit_code != 0:
                    logger.warning(
                        "Failed to clone repo for agent %s: %s",
                        agent.id,
                        proc.stderr,
                    )
                else:
                    logger.info("Cloned repo for engineer %s", agent.id)

                # Configure git user for commits
                await sandbox.process.start(
                    "git config --global user.email 'engineer@aict.local'"
                )
                await sandbox.process.start(
                    "git config --global user.name 'AICT Engineer'"
                )

            elif agent.role == "manager":
                # Manager gets access to spec files (copy from host or clone spec repo)
                if project.spec_repo_path:
                    logger.info("Manager sandbox initialized for project %s", project.id)

        except Exception as exc:
            logger.warning(
                "Sandbox initialization failed for agent %s: %s",
                agent.id,
                exc,
            )

    async def create_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        persistent: bool,
    ) -> SandboxMetadata:
        """
        Create a new sandbox for an agent.
        
        For engineers, the project code repo is cloned.
        For managers, spec files are made available.
        """
        sandbox_id = ""
        sandbox = None
        project = await self._get_project(session, agent.project_id)

        if self._should_use_real_provider():
            try:
                self._apply_sdk_api_key()
                sandbox = await AsyncSandbox.create(
                    template=settings.e2b_template_id or None,
                    timeout=settings.e2b_timeout_seconds,
                    metadata={
                        "agent_id": str(agent.id),
                        "project_id": str(agent.project_id),
                        "role": agent.role,
                    },
                )
                sandbox_id = (
                    getattr(sandbox, "sandbox_id", None)
                    or getattr(sandbox, "id", None)
                    or ""
                )
                if not sandbox_id:
                    raise RuntimeError("E2B returned no sandbox ID")

                # Initialize sandbox with project setup
                await self._initialize_sandbox(sandbox, agent, project)

            except Exception as exc:  # pragma: no cover - network/provider path
                logger.exception(
                    "Failed to create E2B sandbox; using local fallback for agent %s: %s",
                    agent.id,
                    exc,
                )

        if not sandbox_id:
            sandbox_id = f"local-sbox-{uuid.uuid4()}"

        agent.sandbox_id = sandbox_id
        agent.sandbox_persist = persistent
        await session.flush()
        return SandboxMetadata(
            sandbox_id=sandbox_id,
            agent_id=str(agent.id),
            persistent=persistent,
            status="running",
        )

    async def get_sandbox(self, session: AsyncSession, agent: Agent) -> SandboxMetadata:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))

        status = "running"
        if (
            self._should_use_real_provider()
            and not self._is_local_fallback_sandbox(agent.sandbox_id)
        ):
            try:
                self._apply_sdk_api_key()
                sandbox = await AsyncSandbox.connect(
                    agent.sandbox_id,
                    timeout=settings.e2b_timeout_seconds,
                )
                running = await sandbox.is_running()
                status = "running" if running else "stopped"
            except Exception as exc:  # pragma: no cover - network/provider path
                logger.warning(
                    "Failed to inspect sandbox %s for agent %s: %s",
                    agent.sandbox_id,
                    agent.id,
                    exc,
                )
                status = "unknown"

        return SandboxMetadata(
            sandbox_id=agent.sandbox_id,
            agent_id=str(agent.id),
            persistent=bool(agent.sandbox_persist),
            status=status,
        )

    async def close_sandbox(self, session: AsyncSession, agent: Agent) -> None:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))

        sandbox_id = agent.sandbox_id
        if (
            self._should_use_real_provider()
            and not self._is_local_fallback_sandbox(sandbox_id)
        ):
            try:
                self._apply_sdk_api_key()
                await AsyncSandbox.kill(sandbox_id)
            except Exception as exc:  # pragma: no cover - network/provider path
                logger.warning(
                    "Failed to kill sandbox %s for agent %s: %s",
                    sandbox_id,
                    agent.id,
                    exc,
                )

        agent.sandbox_id = None
        await session.flush()

