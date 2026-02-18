"""
Task repository: queries for tasks table.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Task
from backend.db.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession):
        super().__init__(Task, session)

    async def get_by_id(self, task_id: UUID) -> Task | None:
        return await self.get(task_id)

    async def list_by_project(self, project_id: UUID) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())
