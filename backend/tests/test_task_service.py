"""
Tests for task service.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import InvalidTaskStatus, TaskNotFoundError, AgentNotFoundError
from backend.db.models import Agent, Project, Task
from backend.core.constants import USER_AGENT_ID
from backend.schemas.task import TaskCreate, TaskUpdate
from backend.services.message_service import MessageService
from backend.services.task_service import (
    TaskService,
    validate_status,
    validate_transition,
    VALID_TRANSITIONS,
)


class TestStatusValidation:
    """Test status validation functions."""

    def test_valid_status(self):
        # Should not raise
        validate_status("backlog")
        validate_status("in_progress")
        validate_status("done")

    def test_invalid_status(self):
        with pytest.raises(InvalidTaskStatus):
            validate_status("invalid_status")

    def test_valid_transitions(self):
        assert validate_transition("backlog", "specifying") is True
        assert validate_transition("backlog", "assigned") is True
        assert validate_transition("in_progress", "in_review") is True
        assert validate_transition("in_review", "done") is True

    def test_invalid_transitions(self):
        assert validate_transition("backlog", "done") is False
        assert validate_transition("done", "backlog") is False
        assert validate_transition("in_progress", "done") is False

    def test_done_is_terminal(self):
        assert VALID_TRANSITIONS["done"] == []


class TestTaskService:
    """Test task service methods."""

    @pytest.fixture
    def service(self, session: AsyncSession):
        return TaskService(session)

    async def test_create_task(
        self, service: TaskService, sample_project: Project, session: AsyncSession
    ):
        data = TaskCreate(
            title="Test Task",
            description="Test description",
        )
        task = await service.create(sample_project.id, data)

        assert task.title == "Test Task"
        assert task.description == "Test description"
        assert task.status == "backlog"
        assert task.critical == 5
        assert task.urgent == 5
        assert task.project_id == sample_project.id

    async def test_create_task_with_custom_values(
        self, service: TaskService, sample_project: Project
    ):
        data = TaskCreate(
            title="High Priority Task",
            status="specifying",
            critical=1,
            urgent=2,
            module_path="backend/api",
        )
        task = await service.create(sample_project.id, data)

        assert task.status == "specifying"
        assert task.critical == 1
        assert task.urgent == 2
        assert task.module_path == "backend/api"

    async def test_create_task_invalid_status(
        self, service: TaskService, sample_project: Project
    ):
        data = TaskCreate(title="Bad Task", status="invalid")
        with pytest.raises(InvalidTaskStatus):
            await service.create(sample_project.id, data)

    async def test_get_task(
        self, service: TaskService, sample_task: Task
    ):
        task = await service.get(sample_task.id)
        assert task.id == sample_task.id
        assert task.title == sample_task.title

    async def test_get_task_not_found(self, service: TaskService):
        import uuid
        with pytest.raises(TaskNotFoundError):
            await service.get(uuid.uuid4())

    async def test_list_by_project(
        self, service: TaskService, sample_project: Project, session: AsyncSession
    ):
        # Create multiple tasks
        await service.create(sample_project.id, TaskCreate(title="Task 1"))
        await service.create(sample_project.id, TaskCreate(title="Task 2"))

        tasks = await service.list_by_project(sample_project.id)
        assert len(tasks) >= 2

    async def test_list_by_status(
        self, service: TaskService, sample_project: Project
    ):
        await service.create(
            sample_project.id,
            TaskCreate(title="Backlog Task", status="backlog")
        )
        await service.create(
            sample_project.id,
            TaskCreate(title="Specifying Task", status="specifying")
        )

        backlog_tasks = await service.list_by_status(sample_project.id, "backlog")
        assert all(t.status == "backlog" for t in backlog_tasks)

    async def test_update_task(
        self, service: TaskService, sample_task: Task
    ):
        data = TaskUpdate(title="Updated Title", description="Updated desc")
        updated = await service.update(sample_task.id, data)

        assert updated.title == "Updated Title"
        assert updated.description == "Updated desc"

    async def test_update_task_status_valid_transition(
        self, service: TaskService, sample_project: Project
    ):
        # Create task in backlog
        task = await service.create(
            sample_project.id,
            TaskCreate(title="Transition Test")
        )
        assert task.status == "backlog"

        # Valid transition: backlog -> specifying
        updated = await service.update_status(task.id, "specifying")
        assert updated.status == "specifying"

    async def test_update_task_status_invalid_transition(
        self, service: TaskService, sample_project: Project
    ):
        task = await service.create(
            sample_project.id,
            TaskCreate(title="Bad Transition")
        )

        # Invalid transition: backlog -> done
        with pytest.raises(InvalidTaskStatus):
            await service.update_status(task.id, "done")

    async def test_assign_task(
        self,
        service: TaskService,
        sample_task: Task,
        sample_engineer: Agent,
        session: AsyncSession,
    ):
        assigned = await service.assign(sample_task.id, sample_engineer.id)

        assert assigned.assigned_agent_id == sample_engineer.id
        assert assigned.status == "assigned"  # Auto-transition
        unread = await MessageService(session).get_unread_for_agent(sample_engineer.id)
        assert any(
            msg.from_agent_id == USER_AGENT_ID
            and msg.message_type == "system"
            and "Task assigned:" in msg.content
            for msg in unread
        )

    async def test_assign_task_invalid_agent(
        self, service: TaskService, sample_task: Task
    ):
        import uuid
        with pytest.raises(AgentNotFoundError):
            await service.assign(sample_task.id, uuid.uuid4())

    async def test_delete_task(
        self, service: TaskService, sample_task: Task
    ):
        result = await service.delete(sample_task.id)
        assert result is True

        with pytest.raises(TaskNotFoundError):
            await service.get(sample_task.id)

    async def test_delete_assigned_task_clears_agent_current_task(
        self,
        service: TaskService,
        sample_project: Project,
        sample_engineer: Agent,
        session: AsyncSession,
    ):
        task = await service.create(sample_project.id, TaskCreate(title="Delete assigned"))
        await service.assign(task.id, sample_engineer.id)

        await service.delete(task.id)
        await session.refresh(sample_engineer)

        assert sample_engineer.current_task_id is None

    async def test_list_by_agent(
        self, service: TaskService, sample_project: Project, sample_engineer: Agent
    ):
        # Create and assign task
        task = await service.create(
            sample_project.id,
            TaskCreate(title="Agent Task")
        )
        await service.assign(task.id, sample_engineer.id)

        tasks = await service.list_by_agent(sample_engineer.id)
        assert any(t.id == task.id for t in tasks)
