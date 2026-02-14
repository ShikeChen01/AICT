"""
Integration flow tests for MVP-0 core paths.
"""

import pytest

from backend.schemas.chat import ChatMessageCreate
from backend.schemas.task import TaskCreate
from backend.schemas.ticket import TicketCreate
from backend.services.chat_service import ChatService
from backend.services.task_service import TaskService
from backend.services.ticket_service import TicketService


@pytest.mark.asyncio
async def test_task_assignment_wakes_engineer_and_prepares_sandbox(
    session,
    sample_project,
    sample_engineer,
):
    task_service = TaskService(session)
    task = await task_service.create(sample_project.id, TaskCreate(title="Assignment wake test"))

    assert sample_engineer.status == "sleeping"
    assert sample_engineer.sandbox_id is None

    await task_service.assign(task.id, sample_engineer.id)
    await session.refresh(sample_engineer)

    assert sample_engineer.status == "active"
    assert sample_engineer.sandbox_id is not None
    assert sample_engineer.current_task_id == task.id


@pytest.mark.asyncio
async def test_ticket_create_wakes_target_and_prepares_sandbox(
    session,
    sample_project,
    sample_gm,
    sample_om,
):
    ticket_service = TicketService(session)
    sample_om.status = "sleeping"
    sample_om.sandbox_id = None
    await session.flush()

    await ticket_service.create(
        sample_project.id,
        sample_gm.id,
        TicketCreate(
            to_agent_id=sample_om.id,
            header="Wake via ticket",
            ticket_type="question",
            initial_message="Need your review",
        ),
    )
    await session.refresh(sample_om)

    assert sample_om.status == "active"
    assert sample_om.sandbox_id is not None


@pytest.mark.asyncio
async def test_user_to_gm_chat_flow_persists_messages(
    session,
    sample_project,
    sample_gm,
):
    chat_service = ChatService(session)
    user_message, gm_message = await chat_service.send_message(
        sample_project.id,
        ChatMessageCreate(content="Please summarize current progress."),
    )

    assert user_message.role == "user"
    assert gm_message.role == "gm"
    assert gm_message.content

    history = await chat_service.get_history(sample_project.id)
    assert len(history) >= 2
    assert history[-2].role == "user"
    assert history[-1].role == "gm"

