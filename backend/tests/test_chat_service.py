"""
Tests for chat service.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import AgentNotFoundError, ProjectNotFoundError
from backend.db.models import Agent, ChatMessage, Project
from backend.schemas.chat import ChatMessageCreate
from backend.services.chat_service import ChatService


class TestChatService:
    """Test chat service methods."""

    @pytest.fixture
    def service(self, session: AsyncSession):
        return ChatService(session)

    async def test_get_history_empty(
        self,
        service: ChatService,
        sample_project: Project,
    ):
        history = await service.get_history(sample_project.id)
        assert history == []

    async def test_get_history(
        self,
        service: ChatService,
        sample_project: Project,
        session: AsyncSession,
    ):
        # Add some messages
        msg1 = ChatMessage(
            project_id=sample_project.id,
            role="user",
            content="Hello",
        )
        msg2 = ChatMessage(
            project_id=sample_project.id,
            role="gm",
            content="Hi there!",
        )
        session.add_all([msg1, msg2])
        await session.flush()

        history = await service.get_history(sample_project.id)
        assert len(history) == 2
        # Should be in chronological order
        assert history[0].role == "user"
        assert history[1].role == "gm"

    async def test_get_history_with_limit(
        self,
        service: ChatService,
        sample_project: Project,
        session: AsyncSession,
    ):
        # Add many messages
        for i in range(20):
            msg = ChatMessage(
                project_id=sample_project.id,
                role="user" if i % 2 == 0 else "gm",
                content=f"Message {i}",
            )
            session.add(msg)
        await session.flush()

        history = await service.get_history(sample_project.id, limit=5)
        assert len(history) == 5

    async def test_get_history_project_not_found(
        self,
        service: ChatService,
    ):
        with pytest.raises(ProjectNotFoundError):
            await service.get_history(uuid.uuid4())

    async def test_send_message(
        self,
        service: ChatService,
        sample_project: Project,
        sample_gm: Agent,
        session: AsyncSession,
    ):
        data = ChatMessageCreate(content="Hello GM!")

        user_msg, gm_msg = await service.send_message(sample_project.id, data)

        assert user_msg.role == "user"
        assert user_msg.content == "Hello GM!"
        assert gm_msg.role == "gm"
        assert len(gm_msg.content) > 0

    async def test_send_message_updates_gm_status(
        self,
        service: ChatService,
        sample_project: Project,
        sample_gm: Agent,
        session: AsyncSession,
    ):
        # GM should be active after message is processed
        data = ChatMessageCreate(content="Test status")
        await service.send_message(sample_project.id, data)

        await session.refresh(sample_gm)
        assert sample_gm.status == "active"

    async def test_send_message_no_gm(
        self,
        service: ChatService,
        sample_project: Project,
        session: AsyncSession,
    ):
        # Remove GM from project
        from sqlalchemy import delete
        from backend.db.models import Agent
        await session.execute(
            delete(Agent).where(
                Agent.project_id == sample_project.id,
                Agent.role == "gm"
            )
        )
        await session.flush()

        data = ChatMessageCreate(content="No GM here")
        with pytest.raises(AgentNotFoundError):
            await service.send_message(sample_project.id, data)

    async def test_send_message_with_attachments(
        self,
        service: ChatService,
        sample_project: Project,
        sample_gm: Agent,
    ):
        data = ChatMessageCreate(
            content="Here are some files",
            attachments=[{"type": "file", "path": "/test.txt"}],
        )

        user_msg, gm_msg = await service.send_message(sample_project.id, data)

        assert user_msg.attachments == [{"type": "file", "path": "/test.txt"}]

    async def test_get_message(
        self,
        service: ChatService,
        sample_project: Project,
        session: AsyncSession,
    ):
        msg = ChatMessage(
            project_id=sample_project.id,
            role="user",
            content="Test message",
        )
        session.add(msg)
        await session.flush()
        await session.refresh(msg)

        retrieved = await service.get_message(msg.id)
        assert retrieved.id == msg.id
        assert retrieved.content == "Test message"

    async def test_get_message_not_found(self, service: ChatService):
        with pytest.raises(ValueError):
            await service.get_message(uuid.uuid4())
