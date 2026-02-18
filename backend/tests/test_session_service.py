"""Unit tests for SessionService (create/end session)."""

from uuid import uuid4

import pytest

from backend.services.session_service import SessionService, get_session_service


@pytest.mark.asyncio
async def test_create_and_end_session(session, sample_manager, sample_project) -> None:
    svc = get_session_service(session)
    sess = await svc.create_session(
        sample_manager.id,
        sample_project.id,
        trigger_message_id=None,
    )
    assert sess.id is not None
    assert sess.agent_id == sample_manager.id
    assert sess.project_id == sample_project.id
    assert sess.status == "running"
    assert sess.iteration_count == 0
    await session.commit()

    await svc.end_session(sess.id, end_reason="normal_end", status="completed")
    await session.commit()
    await session.refresh(sess)
    assert sess.status == "completed"
    assert sess.end_reason == "normal_end"
    assert sess.ended_at is not None


@pytest.mark.asyncio
async def test_end_session_force(session, sample_manager, sample_project) -> None:
    svc = get_session_service(session)
    sess = await svc.create_session(sample_manager.id, sample_project.id)
    await session.commit()

    await svc.end_session_force(sess.id, "interrupted")
    await session.commit()
    await session.refresh(sess)
    assert sess.status == "force_ended"
    assert sess.end_reason == "interrupted"


@pytest.mark.asyncio
async def test_list_by_agent(session, sample_manager, sample_project) -> None:
    svc = get_session_service(session)
    s1 = await svc.create_session(sample_manager.id, sample_project.id)
    await session.commit()
    await svc.end_session(s1.id, end_reason="normal_end")
    await session.commit()

    listed = await svc.list_by_agent(sample_manager.id, limit=10)
    assert len(listed) >= 1
    assert any(s.id == s1.id for s in listed)
