"""
Tests for SQLAlchemy models — creation, defaults, relationships, constraints.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Project, Task


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

    from backend.services.orchestrator import sandbox_should_persist

    assert agent.id is not None
    assert agent.status == "sleeping"
    assert sandbox_should_persist(agent.role) is False
    assert agent.current_task_id is None
    assert agent.sandbox is None


@pytest.mark.asyncio
async def test_gm_agent_fields(sample_gm: Agent):
    from backend.services.orchestrator import sandbox_should_persist
    assert sample_gm.role == "manager"  # sample_gm is alias for sample_manager
    assert sandbox_should_persist(sample_gm.role) is True
    assert sample_gm.display_name == "Manager"


@pytest.mark.asyncio
async def test_om_agent_fields(sample_om: Agent):
    from backend.services.orchestrator import sandbox_should_persist
    assert sample_om.role == "cto"  # sample_om is alias for sample_cto
    assert sandbox_should_persist(sample_om.role) is True


@pytest.mark.asyncio
async def test_agent_project_relationship(
    session: AsyncSession, sample_project: Project, sample_gm: Agent
):
    result = await session.execute(
        select(Agent).where(Agent.project_id == sample_project.id, Agent.role == "manager")
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
