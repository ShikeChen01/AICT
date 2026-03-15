"""
Integration flow tests for MVP-0 core paths (docs-first: no tickets).
"""

import pytest
from sqlalchemy.orm import selectinload

from backend.db.models import Agent
from backend.schemas.task import TaskCreate
from backend.services.task_service import TaskService


@pytest.mark.asyncio
async def test_task_assignment_wakes_engineer_and_prepares_sandbox(
    session,
    sample_project,
    sample_engineer,
):
    task_service = TaskService(session)
    task = await task_service.create(sample_project.id, TaskCreate(title="Assignment wake test"))

    assert sample_engineer.status == "sleeping"
    assert sample_engineer.sandbox is None

    await task_service.assign(task.id, sample_engineer.id)

    # Re-fetch with eager loading to safely access sandbox relationship
    from sqlalchemy import select
    result = await session.execute(
        select(Agent).options(selectinload(Agent.sandbox)).where(Agent.id == sample_engineer.id)
    )
    refreshed = result.scalar_one()

    assert refreshed.status == "active"
    assert refreshed.current_task_id == task.id


@pytest.mark.skip(reason="Tickets deprecated; use send_message to wake agent")
async def test_ticket_create_wakes_target_and_prepares_sandbox(
    session,
    sample_project,
    sample_gm,
    sample_om,
):
    """Replaced by: send message to agent via POST /api/v1/messages/send (wakes agent)."""
    pass

