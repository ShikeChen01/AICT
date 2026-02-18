"""
Project settings repository.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProjectSettings
from backend.db.repositories.base import BaseRepository


class ProjectSettingsRepository(BaseRepository[ProjectSettings]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProjectSettings, session)

    async def get_by_project(self, project_id: UUID) -> ProjectSettings | None:
        result = await self.session.execute(
            select(ProjectSettings).where(ProjectSettings.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_defaults(self, project_id: UUID) -> ProjectSettings:
        """Get existing settings or create with defaults."""
        settings = await self.get_by_project(project_id)
        if settings:
            return settings
        settings = ProjectSettings(project_id=project_id)
        await self.create(settings)
        return settings
