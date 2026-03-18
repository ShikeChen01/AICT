"""Unit tests for message_service (channel messages)."""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ChannelMessage, Repository
from backend.services.message_service import MessageService


@pytest.fixture
def message_service(session: AsyncSession) -> MessageService:
    return MessageService(session)


@pytest.mark.asyncio
async def test_send_user_to_agent(
    message_service: MessageService,
    sample_project: Repository,
    sample_manager: "Agent",
) -> None:
    from backend.db.models import Agent

    user_id = uuid4()
    msg = await message_service.send_user_to_agent(
        target_agent_id=sample_manager.id,
        project_id=sample_project.id,
        content="Hello agent",
        user_id=user_id,
    )
    assert msg.id is not None
    assert msg.project_id == sample_project.id
    assert msg.from_agent_id is None
    assert msg.from_user_id == user_id
    assert msg.target_agent_id == sample_manager.id
    assert msg.target_user_id is None
    assert msg.content == "Hello agent"
    assert msg.message_type == "normal"
    assert msg.status == "sent"
    assert msg.broadcast is False
    assert msg.is_from_user is True
    assert msg.is_to_user is False


@pytest.mark.asyncio
async def test_send_agent_to_user(
    message_service: MessageService,
    sample_project: Repository,
    sample_manager: "Agent",
) -> None:
    target_user_id = uuid4()
    msg = await message_service.send_agent_to_user(
        from_agent_id=sample_manager.id,
        target_user_id=target_user_id,
        project_id=sample_project.id,
        content="Agent replies",
    )
    assert msg.from_agent_id == sample_manager.id
    assert msg.from_user_id is None
    assert msg.target_agent_id is None
    assert msg.target_user_id == target_user_id
    assert msg.is_from_user is False
    assert msg.is_to_user is True


@pytest.mark.asyncio
async def test_list_conversation(
    message_service: MessageService,
    session: AsyncSession,
    sample_project: Repository,
    sample_manager: "Agent",
) -> None:
    from backend.db.models import Agent

    user_id = uuid4()
    await message_service.send_user_to_agent(
        target_agent_id=sample_manager.id,
        project_id=sample_project.id,
        content="User says hi",
        user_id=user_id,
    )
    await message_service.send_agent_to_user(
        from_agent_id=sample_manager.id,
        target_user_id=user_id,
        project_id=sample_project.id,
        content="Agent replies",
    )
    await session.commit()

    messages = await message_service.list_conversation(
        project_id=sample_project.id,
        agent_id=sample_manager.id,
        limit=10,
    )
    assert len(messages) == 2
    contents = [m.content for m in messages]
    assert "User says hi" in contents
    assert "Agent replies" in contents


@pytest.mark.asyncio
async def test_list_all_user_messages(
    message_service: MessageService,
    session: AsyncSession,
    sample_project: Repository,
    sample_manager: "Agent",
    sample_engineer: "Agent",
) -> None:
    user_id = uuid4()
    await message_service.send_user_to_agent(
        target_agent_id=sample_manager.id,
        project_id=sample_project.id,
        content="To manager",
        user_id=user_id,
    )
    await message_service.send_user_to_agent(
        target_agent_id=sample_engineer.id,
        project_id=sample_project.id,
        content="To engineer",
        user_id=user_id,
    )
    await session.commit()

    messages = await message_service.list_all_user_messages(
        project_id=sample_project.id,
        limit=10,
    )
    assert len(messages) >= 2
    contents = [m.content for m in messages]
    assert "To manager" in contents
    assert "To engineer" in contents


@pytest.mark.asyncio
async def test_mark_received(
    message_service: MessageService,
    session: AsyncSession,
    sample_project: Repository,
    sample_manager: "Agent",
) -> None:
    msg = await message_service.send_user_to_agent(
        target_agent_id=sample_manager.id,
        project_id=sample_project.id,
        content="Hi",
    )
    await session.commit()
    assert msg.status == "sent"

    await message_service.mark_received([msg.id])
    await session.commit()

    from backend.db.repositories.messages import ChannelMessageRepository
    repo = ChannelMessageRepository(session)
    updated = await repo.get(msg.id)
    assert updated is not None
    assert updated.status == "received"


@pytest.mark.asyncio
async def test_broadcast(
    message_service: MessageService,
    sample_project: Repository,
    sample_manager: "Agent",
) -> None:
    msg = await message_service.broadcast(
        from_agent_id=sample_manager.id,
        project_id=sample_project.id,
        content="Broadcast to all",
    )
    assert msg.id is not None
    assert msg.from_agent_id == sample_manager.id
    assert msg.target_agent_id is None
    assert msg.target_user_id is None
    assert msg.broadcast is True
    assert msg.content == "Broadcast to all"
    assert msg.is_from_user is False
    assert msg.is_to_user is False
