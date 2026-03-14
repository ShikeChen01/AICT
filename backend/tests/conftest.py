"""
Shared test fixtures.

Uses SQLite in-memory by default for fast unit tests.
Set INTEGRATION_TEST=1 to use PostgreSQL via testcontainers for integration tests.
"""

import json
import os
import uuid

# Disable Cloud Logging in tests so we don't need GCP credentials or network
os.environ["USE_CLOUD_LOGGING"] = "false"
os.environ.pop("K_SERVICE", None)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Agent, Base, Project, Repository, Task

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


_CI_DATABASE = bool(os.getenv("DATABASE_URL"))


@pytest_asyncio.fixture
async def engine(postgres_container):
    """
    Create database engine.
    - Uses DATABASE_URL env if set (CI with service container — schema via Alembic)
    - Uses PostgreSQL via testcontainers if INTEGRATION_TEST=1
    - Uses SQLite in-memory otherwise (faster for unit tests)
    """
    from sqlalchemy import text as sa_text

    db_url = os.getenv("DATABASE_URL")
    if USE_POSTGRES and db_url:
        eng = create_async_engine(db_url, echo=False)
    elif USE_POSTGRES and postgres_container:
        url = postgres_container.get_connection_url()
        url = url.replace("psycopg2", "asyncpg")
        eng = create_async_engine(url, echo=False)
    else:
        eng = create_async_engine(
            "sqlite+aiosqlite://",
            echo=False,
            json_serializer=lambda obj: json.dumps(obj),
            json_deserializer=lambda s: json.loads(s) if s else None,
        )

    if _CI_DATABASE:
        # Schema already created by `alembic upgrade head` in CI;
        # calling create_all/drop_all would conflict with migration-managed
        # constraint names (e.g. fk_agents_current_task vs fk_agent_current_task).
        pass
    else:
        async with eng.begin() as conn:
            if USE_POSTGRES:
                await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

    yield eng

    if not _CI_DATABASE:
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
async def sample_project(session: AsyncSession) -> Repository:
    """Create a test project (Repository)."""
    project = Repository(
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
async def sample_manager(session: AsyncSession, sample_project: Repository) -> Agent:
    """Manager agent (GM)."""
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="manager",
        display_name="Manager",
        model="",
        status="sleeping",
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_cto(session: AsyncSession, sample_project: Repository) -> Agent:
    """CTO agent."""
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="cto",
        display_name="CTO",
        model="",
        status="sleeping",
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_engineer(session: AsyncSession, sample_project: Repository) -> Agent:
    """Create an Engineer agent."""
    agent = Agent(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        role="engineer",
        display_name="Engineer-1",
        model="",
        status="sleeping",
    )
    session.add(agent)
    await session.flush()
    return agent


@pytest_asyncio.fixture
async def sample_task(session: AsyncSession, sample_project: Repository) -> Task:
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


@pytest_asyncio.fixture
async def sample_gm(sample_manager: Agent) -> Agent:
    """Alias for sample_manager (GM)."""
    return sample_manager


@pytest_asyncio.fixture
async def sample_om(sample_cto: Agent) -> Agent:
    """Alias for sample_cto (legacy name; use sample_cto)."""
    return sample_cto
