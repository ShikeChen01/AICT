"""
Tests for agent status + queue API composition (docs: queue_size, pending_message_count).
"""

import pytest

from backend.api.v1.agents import list_agent_status
from backend.core.constants import USER_AGENT_ID
from backend.schemas.task import TaskCreate
from backend.services.message_service import get_message_service
from backend.services.task_service import TaskService


@pytest.mark.asyncio
async def test_list_agent_status_includes_queue_and_pending_message_count(
    session,
    sample_project,
    sample_gm,
    sample_engineer,
):
    task_service = TaskService(session)
    msg_service = get_message_service(session)

    task = await task_service.create(sample_project.id, TaskCreate(title="Queued task"))
    await task_service.assign(task.id, sample_engineer.id)

    await msg_service.send_user_to_agent(
        target_agent_id=sample_engineer.id,
        project_id=sample_project.id,
        content="Please investigate regression",
    )
    await session.commit()

    rows = await list_agent_status(
        project_id=sample_project.id,
        _auth=True,
        db=session,
    )
    engineer = next(row for row in rows if row.id == sample_engineer.id)

    assert engineer.queue_size >= 1
    assert engineer.pending_message_count >= 1
    assert any(item.id == task.id for item in engineer.task_queue)

