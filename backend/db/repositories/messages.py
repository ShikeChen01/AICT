"""
Channel and agent message repositories.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AgentMessage, ChannelMessage
from backend.db.repositories.base import BaseRepository


class ChannelMessageRepository(BaseRepository[ChannelMessage]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChannelMessage, session)

    async def create_message(
        self,
        project_id: UUID,
        content: str,
        *,
        from_agent_id: UUID | None = None,
        target_agent_id: UUID | None = None,
        message_type: str = "normal",
        broadcast: bool = False,
    ) -> ChannelMessage:
        msg = ChannelMessage(
            project_id=project_id,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            content=content,
            message_type=message_type,
            status="sent",
            broadcast=broadcast,
        )
        await self.create(msg)
        return msg

    async def list_by_target_and_status(
        self,
        target_agent_id: UUID,
        status: str = "sent",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        result = await self.session.execute(
            select(ChannelMessage)
            .where(
                ChannelMessage.target_agent_id == target_agent_id,
                ChannelMessage.status == status,
            )
            .order_by(ChannelMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_conversation(
        self,
        project_id: UUID,
        agent_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        """Messages between user (USER_AGENT_ID) and the given agent, either direction."""
        from backend.core.constants import USER_AGENT_ID

        result = await self.session.execute(
            select(ChannelMessage)
            .where(ChannelMessage.project_id == project_id)
            .where(
                (
                    (ChannelMessage.from_agent_id == USER_AGENT_ID)
                    & (ChannelMessage.target_agent_id == agent_id)
                )
                | (
                    (ChannelMessage.from_agent_id == agent_id)
                    & (ChannelMessage.target_agent_id == USER_AGENT_ID)
                )
            )
            .order_by(ChannelMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all_user_messages(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        """All messages to/from user in the project (for activity view)."""
        from backend.core.constants import USER_AGENT_ID

        result = await self.session.execute(
            select(ChannelMessage)
            .where(ChannelMessage.project_id == project_id)
            .where(
                (ChannelMessage.from_agent_id == USER_AGENT_ID)
                | (ChannelMessage.target_agent_id == USER_AGENT_ID)
            )
            .order_by(ChannelMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def mark_received(self, message_ids: list[UUID]) -> None:
        if not message_ids:
            return
        await self.session.execute(
            update(ChannelMessage).where(ChannelMessage.id.in_(message_ids)).values(status="received")
        )
        await self.session.flush()

    async def mark_read(self, message_ids: list[UUID]) -> None:
        """Mark messages as read by the user."""
        if not message_ids:
            return
        await self.session.execute(
            update(ChannelMessage).where(ChannelMessage.id.in_(message_ids)).values(status="read")
        )
        await self.session.flush()

    async def get_undelivered_for_replay(self) -> list[ChannelMessage]:
        """All messages with status=sent and non-null target (for replay on startup)."""
        result = await self.session.execute(
            select(ChannelMessage)
            .where(ChannelMessage.status == "sent")
            .where(ChannelMessage.target_agent_id.isnot(None))
            .order_by(ChannelMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_unread_by_targets(
        self, target_agent_ids: list[UUID]
    ) -> dict[UUID, int]:
        """Count messages with status=sent per target_agent_id."""
        from sqlalchemy import func

        if not target_agent_ids:
            return {}
        result = await self.session.execute(
            select(ChannelMessage.target_agent_id, func.count(ChannelMessage.id))
            .where(ChannelMessage.target_agent_id.in_(target_agent_ids))
            .where(ChannelMessage.status == "sent")
            .group_by(ChannelMessage.target_agent_id)
        )
        return dict(result.all())


class AgentMessageRepository(BaseRepository[AgentMessage]):
    def __init__(self, session: AsyncSession):
        super().__init__(AgentMessage, session)

    async def list_by_session(
        self,
        session_id: UUID,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AgentMessage]:
        """Messages for a session, ordered by created_at (conversation order)."""
        result = await self.session.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create_message(
        self,
        agent_id: UUID,
        project_id: UUID,
        role: str,
        content: str,
        loop_iteration: int,
        *,
        session_id: UUID | None = None,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: str | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            agent_id=agent_id,
            session_id=session_id,
            project_id=project_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            loop_iteration=loop_iteration,
        )
        await self.create(msg)
        return msg
