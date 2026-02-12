"""
Tests for SQLAlchemy models — creation, defaults, relationships, constraints.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    Agent,
    ChatMessage,
    Project,
    Task,
    Ticket,
    TicketMessage,
)


# ── Project ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_project(session: AsyncSession):
    project = Project(
        name="MVP-0",
        description="First milestone",
        spec_repo_path="/data/specs/mvp0",
        code_repo_url="https://github.com/user/mvp0",
        code_repo_path="/data/project/mvp0",
    )
    session.add(project)
    await session.flush()

    assert project.id is not None
    assert project.name == "MVP-0"
    assert project.created_at is not None
    assert project.updated_at is not None


@pytest.mark.asyncio
async def test_project_persists(session: AsyncSession):
    pid = uuid.uuid4()
    project = Project(
        id=pid,
        name="Persist Test",
        spec_repo_path="/x",
        code_repo_url="https://example.com",
        code_repo_path="/y",
    )
    session.add(project)
    await session.flush()

    result = await session.execute(select(Project).where(Project.id == pid))
    fetched = result.scalar_one()
    assert fetched.name == "Persist Test"


# ── Agent ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_agent_defaults(session: AsyncSession, sample_project: Project):
    agent = Agent(
        project_id=sample_project.id,
        role="engineer",
        display_name="Engineer-99",
        model="claude-4.5",
    )
    session.add(agent)
    await session.flush()

    assert agent.id is not None
    assert agent.status == "sleeping"
    assert agent.sandbox_persist is False
    assert agent.priority == 2
    assert agent.current_task_id is None
    assert agent.sandbox_id is None


@pytest.mark.asyncio
async def test_gm_agent_fields(sample_gm: Agent):
    assert sample_gm.role == "gm"
    assert sample_gm.priority == 0
    assert sample_gm.sandbox_persist is True
    assert sample_gm.display_name == "GM"


@pytest.mark.asyncio
async def test_om_agent_fields(sample_om: Agent):
    assert sample_om.role == "om"
    assert sample_om.priority == 1
    assert sample_om.sandbox_persist is True


@pytest.mark.asyncio
async def test_agent_project_relationship(
    session: AsyncSession, sample_project: Project, sample_gm: Agent
):
    result = await session.execute(
        select(Agent).where(Agent.project_id == sample_project.id, Agent.role == "gm")
    )
    fetched = result.scalar_one()
    assert fetched.id == sample_gm.id


# ── Task ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_defaults(session: AsyncSession, sample_project: Project):
    task = Task(
        project_id=sample_project.id,
        title="Default task",
    )
    session.add(task)
    await session.flush()

    assert task.status == "backlog"
    assert task.critical == 5
    assert task.urgent == 5
    assert task.assigned_agent_id is None
    assert task.git_branch is None
    assert task.pr_url is None


@pytest.mark.asyncio
async def test_task_custom_priority(session: AsyncSession, sample_project: Project):
    task = Task(
        project_id=sample_project.id,
        title="Critical task",
        critical=0,
        urgent=0,
    )
    session.add(task)
    await session.flush()

    assert task.critical == 0
    assert task.urgent == 0


@pytest.mark.asyncio
async def test_task_assignment(
    session: AsyncSession, sample_task: Task, sample_engineer: Agent
):
    sample_task.assigned_agent_id = sample_engineer.id
    sample_task.status = "assigned"
    await session.flush()

    result = await session.execute(select(Task).where(Task.id == sample_task.id))
    fetched = result.scalar_one()
    assert fetched.assigned_agent_id == sample_engineer.id
    assert fetched.status == "assigned"


@pytest.mark.asyncio
async def test_task_subtask_relationship(session: AsyncSession, sample_project: Project):
    parent = Task(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        title="Parent task",
    )
    session.add(parent)
    await session.flush()

    child = Task(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        title="Child task",
        parent_task_id=parent.id,
    )
    session.add(child)
    await session.flush()

    assert child.parent_task_id == parent.id

    result = await session.execute(
        select(Task).where(Task.parent_task_id == parent.id)
    )
    children = result.scalars().all()
    assert len(children) == 1
    assert children[0].title == "Child task"


# ── Ticket ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_ticket(
    session: AsyncSession,
    sample_project: Project,
    sample_engineer: Agent,
    sample_om: Agent,
):
    ticket = Ticket(
        project_id=sample_project.id,
        from_agent_id=sample_engineer.id,
        to_agent_id=sample_om.id,
        header="Need help with auth module",
        ticket_type="help",
        critical=3,
        urgent=2,
    )
    session.add(ticket)
    await session.flush()

    assert ticket.id is not None
    assert ticket.status == "open"
    assert ticket.closed_at is None
    assert ticket.closed_by_id is None


@pytest.mark.asyncio
async def test_ticket_message(
    session: AsyncSession,
    sample_project: Project,
    sample_engineer: Agent,
    sample_om: Agent,
):
    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        from_agent_id=sample_engineer.id,
        to_agent_id=sample_om.id,
        header="Question about schema",
        ticket_type="question",
    )
    session.add(ticket)
    await session.flush()

    msg = TicketMessage(
        ticket_id=ticket.id,
        from_agent_id=sample_engineer.id,
        content="What format for the auth response?",
    )
    session.add(msg)
    await session.flush()

    assert msg.id is not None
    assert msg.ticket_id == ticket.id

    result = await session.execute(
        select(TicketMessage).where(TicketMessage.ticket_id == ticket.id)
    )
    messages = result.scalars().all()
    assert len(messages) == 1


# ── Chat Messages ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_chat_message(session: AsyncSession, sample_project: Project):
    msg = ChatMessage(
        project_id=sample_project.id,
        role="user",
        content="I want to build an auth system",
    )
    session.add(msg)
    await session.flush()

    assert msg.id is not None
    assert msg.role == "user"
    assert msg.attachments is None


@pytest.mark.asyncio
async def test_chat_message_gm_role(session: AsyncSession, sample_project: Project):
    msg = ChatMessage(
        project_id=sample_project.id,
        role="gm",
        content="Sure, let me break that down for you.",
    )
    session.add(msg)
    await session.flush()

    assert msg.role == "gm"


@pytest.mark.asyncio
async def test_chat_history_ordering(session: AsyncSession, sample_project: Project):
    for i in range(5):
        session.add(
            ChatMessage(
                project_id=sample_project.id,
                role="user" if i % 2 == 0 else "gm",
                content=f"Message {i}",
            )
        )
    await session.flush()

    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == sample_project.id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    assert len(messages) == 5
    assert messages[0].content == "Message 0"
    assert messages[4].content == "Message 4"
