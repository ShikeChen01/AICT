"""
Session service: create/end agent sessions, link agent_messages.

Sessions track each agent work session (wake-to-END). Used by the loop.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AgentMessage, AgentSession
from backend.db.repositories.messages import AgentMessageRepository
from backend.db.repositories.sessions import AgentSessionRepository


class SessionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._repo = AgentSessionRepository(session)
        self._msg_repo = AgentMessageRepository(session)

    async def create_session(
        self,
        agent_id: UUID,
        project_id: UUID,
        *,
        task_id: UUID | None = None,
        trigger_message_id: UUID | None = None,
    ) -> AgentSession:
        sess = await self._repo.create_session(
            agent_id=agent_id,
            project_id=project_id,
            task_id=task_id,
            trigger_message_id=trigger_message_id,
        )
        return sess

    async def end_session(
        self,
        session_id: UUID,
        *,
        end_reason: str,
        status: str = "completed",
    ) -> None:
        """end_reason: normal_end | max_iterations | max_loopbacks | interrupted | aborted | error."""
        await self._repo.end_session(
            session_id=session_id,
            end_reason=end_reason,
            status=status,
        )

    async def end_session_force(self, session_id: UUID, end_reason: str) -> None:
        """Mark session as force_ended (e.g. interrupted, max_iterations)."""
        await self._repo.end_session(
            session_id=session_id,
            end_reason=end_reason,
            status="force_ended",
        )

    async def end_session_error(self, session_id: UUID) -> None:
        """Mark session as error."""
        await self._repo.end_session(
            session_id=session_id,
            end_reason="error",
            status="error",
        )

    async def increment_iteration(self, session_id: UUID) -> None:
        await self._repo.increment_iteration(session_id)

    async def list_by_agent(
        self,
        agent_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentSession]:
        return await self._repo.list_by_agent(agent_id=agent_id, limit=limit, offset=offset)

    async def list_by_project(
        self,
        project_id: UUID,
        agent_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentSession]:
        return await self._repo.list_by_project(
            project_id=project_id,
            agent_id=agent_id,
            limit=limit,
            offset=offset,
        )

    async def get_session_messages(
        self,
        session_id: UUID,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AgentMessage]:
        return await self._msg_repo.list_by_session(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )


def get_session_service(session: AsyncSession) -> SessionService:
    return SessionService(session)
