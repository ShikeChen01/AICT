"""
Shared test fixtures.

Uses SQLite in-memory by default for fast unit tests.
Set INTEGRATION_TEST=1 to use PostgreSQL via testcontainers for integration tests.
"""

import json
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Agent, Base, ChatMessage, Project, Task, Ticket, TicketMessage

# Use PostgreSQL when INTEGRATION_TEST=1, else SQLite for fast unit tests
USE_POSTGRES = os.getenv("INTEGRATION_TEST") == "1"

# Store the postgres container at module level for session scope
_postgres_container = None


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires PostgreSQL)"
    )


@pytest.fixture(scope="session")
def postgres_container():
    """
    Session-scoped PostgreSQL container for integration tests.
    Only starts when INTEGRATION_TEST=1.
    """
    global _postgres_container
    
    if not USE_POSTGRES:
        yield None
        return
    
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed; run: pip install testcontainers[postgres]")
        return
    
    # Start the container
    container = PostgresContainer("postgres:16-alpine")
    container.start()
    _postgres_container = container
    
    yield container
    
    # Cleanup
    container.stop()
    _postgres_container = None


@pytest_asyncio.fixture
async def engine(postgres_container):
    """
    Create database engine.
    - Uses PostgreSQL if INTEGRATION_TEST=1
    - Uses SQLite in-memory otherwise (faster for unit tests)
    """
    if USE_POSTGRES and postgres_container:
        # Convert psycopg2 URL to asyncpg URL
        url = postgres_container.get_connection_url()
        url = url.replace("psycopg2", "asyncpg")
        eng = create_async_engine(url, echo=False)
    else:
        # SQLite for fast unit tests - requires explicit JSON serialization
        eng = create_async_engine(
            "sqlite+aiosqlite://",
            echo=False,
            json_serializer=lambda obj: json.dumps(obj),
            json_deserializer=lambda s: json.loads(s) if s else None,
        )
    
    # Create all tables
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield eng
    
    # Drop all tables and dispose
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    """Create a database session for tests."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def sample_project(session: AsyncSession) -> Project:
    """Create a test project."""
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
    """Create a GM agent."""
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
    """Create an Operations Manager agent."""
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
    """Create an Engineer agent."""
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
    """Create a test task."""
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


@pytest_asyncio.fixture
async def sample_task_assigned(
    session: AsyncSession, sample_task: Task, sample_engineer: Agent
) -> Task:
    """Create a task assigned to an engineer."""
    sample_task.assigned_agent_id = sample_engineer.id
    sample_task.status = "in_progress"
    await session.flush()
    return sample_task
