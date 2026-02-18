"""
Agent repository: queries for agents table.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent
from backend.db.repositories.base import BaseRepository


class AgentRepository(BaseRepository[Agent]):
    def __init__(self, session: AsyncSession):
        super().__init__(Agent, session)

    async def get_by_id(self, agent_id: UUID) -> Agent | None:
        return await self.get(agent_id)

    async def list_by_project(self, project_id: UUID) -> list[Agent]:
        result = await self.session.execute(
            select(Agent).where(Agent.project_id == project_id).order_by(Agent.created_at)
        )
        return list(result.scalars().all())
