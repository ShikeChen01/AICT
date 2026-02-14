"""
Shared test fixtures.

Uses SQLite in-memory via aiosqlite so tests run without PostgreSQL.
"""

import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Agent, Base, ChatMessage, Project, Task, Ticket, TicketMessage


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


@pytest_asyncio.fixture
async def sample_project(session: AsyncSession) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        description="A test project",
        spec_repo_path="/data/specs/test",
        code_repo_url="https://github.com/test/repo",
        code_repo_path="/data/project/test",
    )
    session.add(project)
    await session.flush()
    return project


@pytest_asyncio.fixture
async def sample_gm(session: AsyncSession, sample_project: Project) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="gm",
        display_name="GM",
        model="gemini-3-pro",
        status="sleeping",
        sandbox_persist=True,
        priority=0,
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_manager(session: AsyncSession, sample_project: Project) -> Agent:
    """Manager agent (unified GM+OM role)."""
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="manager",
        display_name="Manager",
        model="claude-4.5-opus",
        status="sleeping",
        sandbox_persist=True,
        priority=0,
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_om(session: AsyncSession, sample_project: Project) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="om",
        display_name="OM-1",
        model="claude-4.5-opus",
        status="sleeping",
        sandbox_persist=True,
        priority=1,
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_engineer(session: AsyncSession, sample_project: Project) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="engineer",
        display_name="Engineer-1",
        model="claude-4.5",
        status="sleeping",
        sandbox_persist=False,
        priority=2,
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_task(session: AsyncSession, sample_project: Project) -> Task:
    task = Task(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        title="Implement auth module",
        description="Build the authentication layer",
        status="backlog",
        critical=3,
        urgent=5,
    )
    session.add(task)
    await session.flush()
    return task
