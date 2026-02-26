"""Repository membership data access."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import RepositoryMembership


class MembershipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_access(self, repository_id: UUID, user_id: UUID) -> bool:
        """Return True if the user has any membership role for this repository."""
        result = await self.session.execute(
            select(
                exists().where(
                    RepositoryMembership.repository_id == repository_id,
                    RepositoryMembership.user_id == user_id,
                )
            )
        )
        return bool(result.scalar())

    async def get(self, repository_id: UUID, user_id: UUID) -> RepositoryMembership | None:
        result = await self.session.execute(
            select(RepositoryMembership).where(
                RepositoryMembership.repository_id == repository_id,
                RepositoryMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        repository_id: UUID,
        user_id: UUID,
        role: str = "member",
    ) -> RepositoryMembership:
        """Add a membership, no-op if already exists (returns existing)."""
        existing = await self.get(repository_id, user_id)
        if existing:
            return existing
        membership = RepositoryMembership(
            id=uuid.uuid4(),
            repository_id=repository_id,
            user_id=user_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def remove(self, repository_id: UUID, user_id: UUID) -> bool:
        membership = await self.get(repository_id, user_id)
        if not membership:
            return False
        await self.session.delete(membership)
        return True

    async def list_by_repository(self, repository_id: UUID) -> list[RepositoryMembership]:
        result = await self.session.execute(
            select(RepositoryMembership).where(
                RepositoryMembership.repository_id == repository_id
            ).order_by(RepositoryMembership.created_at)
        )
        return list(result.scalars().all())
