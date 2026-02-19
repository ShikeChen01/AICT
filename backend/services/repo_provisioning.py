"""
Repository provisioning service.

Ensures project spec/code paths exist and attempts to clone code repositories
when configured.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import Project
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


def _is_real_repo_url(repo_url: str) -> bool:
    if not repo_url:
        return False
    normalized = repo_url.lower().strip()
    if "placeholder" in normalized:
        return False
    return normalized.startswith("https://") or normalized.startswith("git@")


class RepoProvisioningService:
    """Provision project repository paths for backend services."""

    async def provision_all_projects(self, session: AsyncSession) -> None:
        result = await session.execute(select(Project))
        projects = list(result.scalars().all())
        for project in projects:
            self._provision_project(project)

    def _provision_project(self, project: Project) -> None:
        spec_root = Path(project.spec_repo_path)
        code_root = Path(project.code_repo_path)

        spec_root.mkdir(parents=True, exist_ok=True)
        code_root.parent.mkdir(parents=True, exist_ok=True)

        if code_root.exists():
            if (code_root / ".git").exists():
                return
            if any(code_root.iterdir()):
                logger.info(
                    "Skipping clone for project %s: code path exists and is non-empty (%s)",
                    project.id,
                    code_root,
                )
                return
        else:
            code_root.mkdir(parents=True, exist_ok=True)

        if not settings.clone_code_repo_on_startup:
            return
        if not _is_real_repo_url(project.code_repo_url):
            return

        # Remove empty dir so git clone can create it cleanly.
        try:
            code_root.rmdir()
        except OSError:
            # Not empty or cannot remove; leave as-is and skip clone.
            return

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", project.code_repo_url, str(code_root)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Cloned code repository for project %s", project.id)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            reason = stderr or stdout or "unknown git clone failure"
            logger.warning(
                "Failed to clone repository for project %s (%s): %s",
                project.id,
                project.code_repo_url,
                reason,
            )
            code_root.mkdir(parents=True, exist_ok=True)

