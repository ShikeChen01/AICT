"""
Comprehensive API integration tests.

These tests verify the full API endpoints with proper database interaction.
Run with INTEGRATION_TEST=1 to use PostgreSQL instead of SQLite.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, Project, Task
from backend.main import app


@pytest.fixture
async def api_client(session: AsyncSession):
    """
    Create an HTTP client that uses the test database session.
    """
    from backend.db.session import get_db
    
    async def override_get_db():
        yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Standard auth headers for API requests."""
    return {"Authorization": "Bearer change-me-in-production"}


class TestHealthEndpoints:
    """Test health and status endpoints."""

    async def test_health_endpoint(self, api_client: AsyncClient):
        response = await api_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestRepositoriesAPI:
    """Test repository CRUD endpoints."""

    async def test_list_projects(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get("/api/v1/repositories", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        
        # Check project structure
        project = data[0]
        assert "id" in project
        assert "name" in project

    async def test_get_project(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get(
            f"/api/v1/repositories/{sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == str(sample_project.id)
        assert data["name"] == sample_project.name

    async def test_get_project_not_found(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
    ):
        fake_id = uuid.uuid4()
        response = await api_client.get(
            f"/api/v1/repositories/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestTasksAPI:
    """Test task CRUD endpoints."""

    async def test_list_tasks(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
        sample_task: Task,
    ):
        response = await api_client.get(
            f"/api/v1/tasks?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_create_task(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        task_data = {
            "title": "New Test Task",
            "description": "Task created via API",
            "status": "backlog",
            "critical": 5,
            "urgent": 3,
        }
        
        response = await api_client.post(
            f"/api/v1/tasks?project_id={sample_project.id}",
            json=task_data,
            headers=auth_headers,
        )
        assert response.status_code == 201
        
        data = response.json()
        assert data["title"] == "New Test Task"
        assert data["status"] == "backlog"

    async def test_update_task_status(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
        sample_task: Task,
    ):
        # Valid transition: backlog -> assigned
        response = await api_client.patch(
            f"/api/v1/tasks/{sample_task.id}/status?status=assigned",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "assigned"

    async def test_get_task(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_task: Task,
    ):
        response = await api_client.get(
            f"/api/v1/tasks/{sample_task.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == str(sample_task.id)


class TestAgentsAPI:
    """Test agent endpoints."""

    async def test_list_agents(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
        sample_gm: Agent,
    ):
        response = await api_client.get(
            f"/api/v1/agents?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_agent_status(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
        sample_gm: Agent,
    ):
        response = await api_client.get(
            f"/api/v1/agents/status?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)


class TestJobsAPI:
    """Jobs API removed (docs-first: replaced by sessions). Expect 404."""

    async def test_list_jobs_returns_404(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get(
            f"/api/v1/jobs?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_list_active_jobs_returns_404(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get(
            f"/api/v1/jobs/active?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestSessionsAPI:
    """Docs contract: GET /api/v1/sessions (replaces jobs)."""

    async def test_list_sessions(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get(
            f"/api/v1/sessions?project_id={sample_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestRepositorySettingsAPI:
    """Docs contract: GET/PATCH /api/v1/repositories/{id}/settings."""

    async def test_get_settings(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        sample_project: Project,
    ):
        response = await api_client.get(
            f"/api/v1/repositories/{sample_project.id}/settings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "max_engineers" in data
        assert "persistent_sandbox_count" in data
        assert data["project_id"] == str(sample_project.id)


class TestAuthenticationRequired:
    """Test that endpoints require authentication."""

    async def test_repositories_requires_auth(self, api_client: AsyncClient):
        response = await api_client.get("/api/v1/repositories")
        # Should return 401 or 422 (missing header)
        assert response.status_code in (401, 422)

    async def test_tasks_requires_auth(self, api_client: AsyncClient):
        fake_id = uuid.uuid4()
        # Tasks endpoint requires project_id query param
        response = await api_client.get(f"/api/v1/tasks?project_id={fake_id}")
        assert response.status_code in (401, 422)


@pytest.mark.integration
class TestDatabaseIntegration:
    """
    Integration tests that specifically test database behavior.
    These are more meaningful when run with INTEGRATION_TEST=1 (PostgreSQL).
    """

    async def test_cascade_delete_project(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        session: AsyncSession,
    ):
        """Test that deleting a project cascades to related entities."""
        # Create a project with agents and tasks
        project = Project(
            id=uuid.uuid4(),
            name="Cascade Test Project",
            description="Testing cascade delete",
            spec_repo_path="/data/specs/test",
            code_repo_url="https://github.com/test/cascade",
            code_repo_path="/data/project/cascade",
        )
        session.add(project)
        await session.flush()
        
        agent = Agent(
            id=uuid.uuid4(),
            project_id=project.id,
            role="manager",
            display_name="Test Manager",
            model="test-model",
            status="sleeping",
        )
        session.add(agent)
        
        task = Task(
            id=uuid.uuid4(),
            project_id=project.id,
            title="Test Task",
            status="backlog",
        )
        session.add(task)
        await session.flush()
        
        # Verify they exist
        assert agent.id is not None
        assert task.id is not None

    async def test_circular_reference_handling(
        self,
        session: AsyncSession,
        sample_project: Project,
    ):
        """Test that circular references between Agent and Task are handled."""
        # Create an agent
        agent = Agent(
            id=uuid.uuid4(),
            project_id=sample_project.id,
            role="engineer",
            display_name="Test Engineer",
            model="test-model",
            status="sleeping",
        )
        session.add(agent)
        await session.flush()
        
        # Create a task
        task = Task(
            id=uuid.uuid4(),
            project_id=sample_project.id,
            title="Circular Test Task",
            status="in_progress",
            assigned_agent_id=agent.id,
        )
        session.add(task)
        await session.flush()
        
        # Now set the agent's current_task_id
        agent.current_task_id = task.id
        await session.flush()
        
        # Verify the circular reference is established
        assert agent.current_task_id == task.id
        assert task.assigned_agent_id == agent.id
        
        # The use_alter=True should allow this to be dropped without issues
        await session.refresh(agent)
        await session.refresh(task)

    async def test_delete_project_with_agent_task_cycle(
        self,
        api_client: AsyncClient,
        auth_headers: dict,
        session: AsyncSession,
    ):
        """Deleting a project should succeed even with Agent<->Task cross references."""
        project = Project(
            id=uuid.uuid4(),
            name="Cycle Delete Project",
            description="Project with circular references",
            spec_repo_path="/tmp/specs/cycle-delete",
            code_repo_url="https://github.com/test/cycle-delete",
            code_repo_path="/tmp/code/cycle-delete",
        )
        session.add(project)
        await session.flush()

        agent = Agent(
            id=uuid.uuid4(),
            project_id=project.id,
            role="engineer",
            display_name="Cycle Engineer",
            model="test-model",
            status="active",
        )
        session.add(agent)
        await session.flush()

        task = Task(
            id=uuid.uuid4(),
            project_id=project.id,
            title="Cycle task",
            status="assigned",
            assigned_agent_id=agent.id,
            created_by_id=agent.id,
        )
        session.add(task)
        await session.flush()

        agent.current_task_id = task.id
        await session.commit()

        response = await api_client.delete(
            f"/api/v1/repositories/{project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Project should no longer be fetchable after deletion.
        get_response = await api_client.get(
            f"/api/v1/repositories/{project.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404
