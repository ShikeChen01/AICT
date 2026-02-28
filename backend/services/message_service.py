"""
Message service: channel message send, list, mark received, broadcast.

All messaging flows through channel_messages. User = USER_AGENT_ID.
Broadcast is write-only (no wake-up signal).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import USER_AGENT_ID
from backend.db.repositories.attachments import AttachmentRepository
from backend.db.repositories.messages import ChannelMessageRepository


class MessageService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._channel_repo = ChannelMessageRepository(session)
        self._attachment_repo = AttachmentRepository(session)

    async def send(
        self,
        from_agent_id: UUID,
        target_agent_id: UUID,
        project_id: UUID,
        content: str,
        *,
        message_type: str = "normal",
        from_user_id: UUID | None = None,
        attachment_ids: list[UUID] | None = None,
    ) -> "ChannelMessage":
        """Send a message from one agent to another (or user to agent). Writes to DB with status=sent."""
        msg = await self._channel_repo.create_message(
            project_id=project_id,
            content=content,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            from_user_id=from_user_id,
            message_type=message_type,
            broadcast=False,
        )
        # Phase 6: link pre-uploaded attachments to this message
        if attachment_ids:
            for position, att_id in enumerate(attachment_ids):
                await self._attachment_repo.link_to_message(
                    message_id=msg.id,
                    attachment_id=att_id,
                    position=position,
                )
        return msg

    async def send_user_to_agent(
        self,
        target_agent_id: UUID,
        project_id: UUID,
        content: str,
        user_id: UUID | None = None,
        attachment_ids: list[UUID] | None = None,
    ) -> "ChannelMessage":
        """Send a message from the user (USER_AGENT_ID) to an agent.

        ``user_id`` is the real authenticated user FK for attribution (from_user_id).
        ``attachment_ids`` links pre-uploaded image attachments to this message.
        """
        return await self.send(
            from_agent_id=USER_AGENT_ID,
            target_agent_id=target_agent_id,
            project_id=project_id,
            content=content,
            from_user_id=user_id,
            attachment_ids=attachment_ids,
        )

    async def list_conversation(
        self,
        project_id: UUID,
        agent_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list["ChannelMessage"]:
        """Messages between user and the given agent (conversation view)."""
        return await self._channel_repo.list_conversation(
            project_id=project_id,
            agent_id=agent_id,
            limit=limit,
            offset=offset,
        )

    async def list_all_user_messages(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list["ChannelMessage"]:
        """All messages to/from user in the project (activity view)."""
        return await self._channel_repo.list_all_user_messages(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )

    async def get_unread_for_agent(
        self,
        target_agent_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list["ChannelMessage"]:
        """Unread (status=sent) channel messages for this agent. Used by the loop."""
        return await self._channel_repo.list_by_target_and_status(
            target_agent_id=target_agent_id,
            status="sent",
            limit=limit,
            offset=offset,
        )

    async def mark_received(self, message_ids: list[UUID]) -> None:
        """Mark messages as received (consumed by target)."""
        await self._channel_repo.mark_received(message_ids)

    async def broadcast(
        self,
        from_agent_id: UUID,
        project_id: UUID,
        content: str,
        *,
        message_type: str = "normal",
    ) -> "ChannelMessage":
        """Write a broadcast message (target_agent_id=NULL, broadcast=true). No wake-up signal."""
        from backend.db.models import ChannelMessage

        msg = await self._channel_repo.create_message(
            project_id=project_id,
            content=content,
            from_agent_id=from_agent_id,
            target_agent_id=None,
            message_type=message_type,
            broadcast=True,
        )
        return msg

    async def get_undelivered_for_replay(self) -> list["ChannelMessage"]:
        """All sent-but-unreceived messages (for MessageRouter replay on startup)."""
        return await self._channel_repo.get_undelivered_for_replay()

    async def count_unread_by_targets(
        self, target_agent_ids: list[UUID]
    ) -> dict[UUID, int]:
        """Count unread (status=sent) messages per target agent. For pending_message_count."""
        return await self._channel_repo.count_unread_by_targets(target_agent_ids)


def get_message_service(session: AsyncSession) -> MessageService:
    return MessageService(session)
