"""Project membership data access."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProjectMembership


class MembershipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_access(self, project_id: UUID, user_id: UUID) -> bool:
        """Return True if the user has any membership role for this project."""
        result = await self.session.execute(
            select(
                exists().where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user_id,
                )
            )
        )
        return bool(result.scalar())

    async def get(self, project_id: UUID, user_id: UUID) -> ProjectMembership | None:
        result = await self.session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        project_id: UUID,
        user_id: UUID,
        role: str = "member",
    ) -> ProjectMembership:
        """Add a membership, no-op if already exists (returns existing)."""
        existing = await self.get(project_id, user_id)
        if existing:
            return existing
        membership = ProjectMembership(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def remove(self, project_id: UUID, user_id: UUID) -> bool:
        membership = await self.get(project_id, user_id)
        if not membership:
            return False
        await self.session.delete(membership)
        return True

    async def list_by_repository(self, project_id: UUID) -> list[ProjectMembership]:
        result = await self.session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id
            ).order_by(ProjectMembership.created_at)
        )
        return list(result.scalars().all())
