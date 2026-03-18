"""
Message service: channel message send, list, mark received, broadcast.

All messaging uses explicit user FKs (from_user_id, target_user_id) to
represent human participants.  Agent participants use from_agent_id /
target_agent_id.  There is no sentinel UUID — NULL simply means "not
applicable" on any given FK column.

Broadcast is write-only (no wake-up signal).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repositories.attachments import AttachmentRepository
from backend.db.repositories.messages import ChannelMessageRepository


class MessageService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._channel_repo = ChannelMessageRepository(session)
        self._attachment_repo = AttachmentRepository(session)

    # ── Send ─────────────────────────────────────────────────────────

    async def send(
        self,
        *,
        from_agent_id: UUID | None = None,
        target_agent_id: UUID | None = None,
        from_user_id: UUID | None = None,
        target_user_id: UUID | None = None,
        project_id: UUID,
        content: str,
        message_type: str = "normal",
        attachment_ids: list[UUID] | None = None,
    ) -> "ChannelMessage":
        """Send a message.  Exactly one of the from_* and one of the target_*
        fields should be populated (the other stays None)."""
        msg = await self._channel_repo.create_message(
            project_id=project_id,
            content=content,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            from_user_id=from_user_id,
            target_user_id=target_user_id,
            message_type=message_type,
            broadcast=False,
        )
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
        """Send a message from a human user to an agent.

        ``user_id`` is the authenticated user FK (from_user_id).
        ``attachment_ids`` links pre-uploaded image attachments to this message.
        """
        return await self.send(
            from_user_id=user_id,
            target_agent_id=target_agent_id,
            project_id=project_id,
            content=content,
            attachment_ids=attachment_ids,
        )

    async def send_agent_to_user(
        self,
        from_agent_id: UUID,
        target_user_id: UUID | None,
        project_id: UUID,
        content: str,
        *,
        message_type: str = "normal",
    ) -> "ChannelMessage":
        """Send a message from an agent to a human user."""
        return await self.send(
            from_agent_id=from_agent_id,
            target_user_id=target_user_id,
            project_id=project_id,
            content=content,
            message_type=message_type,
        )

    # ── Read ─────────────────────────────────────────────────────────

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

    # ── Broadcast ────────────────────────────────────────────────────

    async def broadcast(
        self,
        from_agent_id: UUID,
        project_id: UUID,
        content: str,
        *,
        message_type: str = "normal",
    ) -> "ChannelMessage":
        """Write a broadcast message (no target, broadcast=true). No wake-up signal."""
        msg = await self._channel_repo.create_message(
            project_id=project_id,
            content=content,
            from_agent_id=from_agent_id,
            target_agent_id=None,
            message_type=message_type,
            broadcast=True,
        )
        return msg

    # ── Replay / counts ──────────────────────────────────────────────

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
