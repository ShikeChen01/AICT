"""Attachment repository — CRUD for binary image blobs and message links."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Attachment, MessageAttachment
from backend.db.repositories.base import BaseRepository


class AttachmentRepository(BaseRepository[Attachment]):
    def __init__(self, session: AsyncSession):
        super().__init__(Attachment, session)

    async def create_attachment(
        self,
        *,
        project_id: UUID,
        uploaded_by_user_id: UUID | None,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> Attachment:
        sha256 = hashlib.sha256(data).hexdigest()
        attachment = Attachment(
            project_id=project_id,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            sha256=sha256,
            data=data,
        )
        await self.create(attachment)
        return attachment

    async def get_by_id(self, attachment_id: UUID) -> Attachment | None:
        result = await self.session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def link_to_message(
        self,
        message_id: UUID,
        attachment_id: UUID,
        position: int = 0,
    ) -> MessageAttachment:
        link = MessageAttachment(
            message_id=message_id,
            attachment_id=attachment_id,
            position=position,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def get_for_messages(
        self, message_ids: list[UUID]
    ) -> dict[UUID, list[Attachment]]:
        """Return a dict mapping message_id → list of Attachment objects (in position order).

        Loads attachment binary data for the given set of message IDs.
        Used by the agent loop to populate LLM image parts.
        """
        if not message_ids:
            return {}

        result = await self.session.execute(
            select(MessageAttachment, Attachment)
            .join(Attachment, MessageAttachment.attachment_id == Attachment.id)
            .where(MessageAttachment.message_id.in_(message_ids))
            .order_by(MessageAttachment.message_id, MessageAttachment.position)
        )
        rows = result.all()

        mapping: dict[UUID, list[Attachment]] = {mid: [] for mid in message_ids}
        for msg_att, attachment in rows:
            mapping[msg_att.message_id].append(attachment)
        return mapping
