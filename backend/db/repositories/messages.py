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
        from_user_id: UUID | None = None,
        message_type: str = "normal",
        broadcast: bool = False,
    ) -> ChannelMessage:
        msg = ChannelMessage(
            project_id=project_id,
            from_agent_id=from_agent_id,
            target_agent_id=target_agent_id,
            from_user_id=from_user_id,
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


# Token estimation constants (word-based, no tokenizer dependency)
_WORDS_PER_TOKEN = 0.75   # 1 token ≈ 0.75 words (conservative estimate)
_FILL_TARGET = 0.95       # fill to 95% of budget, 5% margin for estimation error


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

    async def list_last_n_sessions(
        self,
        agent_id: UUID,
        current_session_id: UUID,
        n_sessions: int = 5,
        messages_per_session: int = 500,
    ) -> list[AgentMessage]:
        """Messages from the last n sessions for this agent (including current),
        ordered oldest-first so they replay in conversation order.

        The current session is always included regardless of n_sessions count.
        """
        from backend.db.models import AgentSession

        # Find the n most recent session IDs for this agent
        session_result = await self.session.execute(
            select(AgentSession.id)
            .where(AgentSession.agent_id == agent_id)
            .order_by(AgentSession.started_at.desc())
            .limit(n_sessions)
        )
        session_ids = [row[0] for row in session_result.all()]

        # Ensure current session is included
        if current_session_id not in session_ids:
            session_ids.append(current_session_id)

        if not session_ids:
            return []

        result = await self.session.execute(
            select(AgentMessage)
            .where(AgentMessage.agent_id == agent_id)
            .where(AgentMessage.session_id.in_(session_ids))
            .order_by(AgentMessage.created_at.asc())
            .limit(messages_per_session * n_sessions)
        )
        return list(result.scalars().all())

    async def list_past_session_history(
        self,
        agent_id: UUID,
        current_session_id: UUID,
        budget_tokens: int,
        n_sessions: int = 5,
    ) -> list[AgentMessage]:
        """Load conversation-only history from past sessions, fitted to budget.

        - Filters out tool messages (role != 'tool') at the SQL level
        - Uses word count as a token estimate (1 token ≈ 0.75 words)
        - Fills to 95% of budget_tokens to leave a safety margin
        - Returns results in chronological order (oldest first)
        - Most recent sessions are prioritized when budget is tight
        """
        from backend.db.models import AgentSession

        target_words = int(budget_tokens * _WORDS_PER_TOKEN * _FILL_TARGET)

        # Get the last N session IDs (excluding current session)
        session_result = await self.session.execute(
            select(AgentSession.id)
            .where(
                AgentSession.agent_id == agent_id,
                AgentSession.id != current_session_id,
            )
            .order_by(AgentSession.started_at.desc())
            .limit(n_sessions)
        )
        session_ids = [row[0] for row in session_result.all()]
        if not session_ids:
            return []

        # Query conversation messages only (no tool role), newest first
        result = await self.session.execute(
            select(AgentMessage)
            .where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.session_id.in_(session_ids),
                AgentMessage.role != "tool",
            )
            .order_by(AgentMessage.created_at.desc())
        )
        messages = list(result.scalars().all())

        # Accumulate newest-first until we approach the word budget
        selected: list[AgentMessage] = []
        accumulated_words = 0
        for msg in messages:
            msg_words = len((msg.content or "").split())
            if accumulated_words + msg_words > target_words:
                break
            selected.append(msg)
            accumulated_words += msg_words

        # Reverse to chronological order
        selected.reverse()
        return selected

    async def list_current_session(
        self,
        agent_id: UUID,
        session_id: UUID,
    ) -> list[AgentMessage]:
        """Return all messages from the current session, in chronological order."""
        result = await self.session.execute(
            select(AgentMessage)
            .where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.session_id == session_id,
            )
            .order_by(AgentMessage.created_at.asc())
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
        tool_output: str | None = None,  # deprecated — kept for backward compat, ignored
    ) -> AgentMessage:
        msg = AgentMessage(
            agent_id=agent_id,
            session_id=session_id,
            project_id=project_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            # tool_output column no longer populated — full results are ephemeral
            loop_iteration=loop_iteration,
        )
        await self.create(msg)
        return msg
