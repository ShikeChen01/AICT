"""
Agent session repository.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AgentSession
from backend.db.repositories.base import BaseRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentSessionRepository(BaseRepository[AgentSession]):
    def __init__(self, session: AsyncSession):
        super().__init__(AgentSession, session)

    async def create_session(
        self,
        agent_id: UUID,
        project_id: UUID,
        *,
        task_id: UUID | None = None,
        trigger_message_id: UUID | None = None,
    ) -> AgentSession:
        sess = AgentSession(
            agent_id=agent_id,
            project_id=project_id,
            task_id=task_id,
            trigger_message_id=trigger_message_id,
            status="running",
            iteration_count=0,
        )
        await self.create(sess)
        return sess

    async def end_session(
        self,
        session_id: UUID,
        *,
        end_reason: str,
        status: str = "completed",
    ) -> None:
        """Mark session as ended. status: completed | force_ended | error."""
        await self.session.execute(
            update(AgentSession)
            .where(AgentSession.id == session_id)
            .values(
                status=status,
                end_reason=end_reason,
                ended_at=_utcnow(),
            )
        )
        await self.session.flush()

    async def increment_iteration(self, session_id: UUID) -> None:
        """Increment iteration_count for the session."""
        sess = await self.get(session_id)
        if sess:
            sess.iteration_count = (sess.iteration_count or 0) + 1
            await self.update(sess)

    async def list_by_agent(
        self,
        agent_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentSession]:
        result = await self.session.execute(
            select(AgentSession)
            .where(AgentSession.agent_id == agent_id)
            .order_by(AgentSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_project(
        self,
        project_id: UUID,
        agent_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentSession]:
        q = (
            select(AgentSession)
            .where(AgentSession.project_id == project_id)
            .order_by(AgentSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if agent_id is not None:
            q = q.where(AgentSession.agent_id == agent_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())
