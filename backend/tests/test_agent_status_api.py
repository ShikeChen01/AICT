"""
Tests for agent status + queue API composition.
"""

import pytest

from backend.api.v1.agents import list_agent_status
from backend.schemas.task import TaskCreate
from backend.schemas.ticket import TicketCreate
from backend.services.task_service import TaskService
from backend.services.ticket_service import TicketService


@pytest.mark.asyncio
async def test_list_agent_status_includes_queue_and_ticket_counts(
    session,
    sample_project,
    sample_gm,
    sample_engineer,
):
    task_service = TaskService(session)
    ticket_service = TicketService(session)

    task = await task_service.create(sample_project.id, TaskCreate(title="Queued task"))
    await task_service.assign(task.id, sample_engineer.id)

    await ticket_service.create(
        sample_project.id,
        sample_gm.id,
        TicketCreate(
            to_agent_id=sample_engineer.id,
            header="Investigate regression",
            ticket_type="issue",
        ),
    )

    rows = await list_agent_status(
        project_id=sample_project.id,
        _auth=True,
        db=session,
    )
    engineer = next(row for row in rows if row.id == sample_engineer.id)

    assert engineer.queue_size >= 1
    assert engineer.open_ticket_count >= 1
    assert any(item.id == task.id for item in engineer.task_queue)

