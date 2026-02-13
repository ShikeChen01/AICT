"""
Task service — handles task CRUD, status transitions, and WebSocket broadcasts.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import InvalidTaskStatus, TaskNotFoundError, AgentNotFoundError
from backend.db.models import Agent, Task, VALID_TASK_STATUSES
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse


# Valid status transitions
# backlog -> specifying -> assigned -> in_progress -> in_review -> done
VALID_TRANSITIONS: dict[str, list[str]] = {
    "backlog": ["specifying", "assigned"],  # Can skip specifying if simple task
    "specifying": ["assigned", "backlog"],  # Can go back to backlog if not ready
    "assigned": ["in_progress", "backlog"],  # Engineer picks up or demoted
    "in_progress": ["in_review", "assigned"],  # Submit for review or back to assigned
    "in_review": ["done", "in_progress"],  # Approved or needs more work
    "done": [],  # Terminal state
}


def validate_status(status: str) -> None:
    """Validate that a status is one of the valid task statuses."""
    if status not in VALID_TASK_STATUSES:
        raise InvalidTaskStatus(status)


def validate_transition(from_status: str, to_status: str) -> bool:
    """Check if a status transition is valid."""
    validate_status(from_status)
    validate_status(to_status)
    allowed = VALID_TRANSITIONS.get(from_status, [])
    return to_status in allowed


class TaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._ws_manager = None  # Lazy import to avoid circular deps
        self._orchestrator = None

    @property
    def ws_manager(self):
        """Lazy load WebSocket manager to avoid circular imports."""
        if self._ws_manager is None:
            from backend.websocket.manager import ws_manager
            self._ws_manager = ws_manager
        return self._ws_manager

    @property
    def orchestrator(self):
        """Lazy load orchestrator to avoid circular imports."""
        if self._orchestrator is None:
            from backend.services.orchestrator import OrchestratorService
            self._orchestrator = OrchestratorService()
        return self._orchestrator

    async def get(self, task_id: UUID) -> Task:
        """Get a task by ID."""
        result = await self.session.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    async def list_by_project(self, project_id: UUID) -> list[Task]:
        """List all tasks for a project."""
        result = await self.session.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.critical, Task.urgent, Task.created_at)
        )
        return list(result.scalars().all())

    async def list_by_status(self, project_id: UUID, status: str) -> list[Task]:
        """List tasks by status within a project."""
        validate_status(status)
        result = await self.session.execute(
            select(Task)
            .where(Task.project_id == project_id, Task.status == status)
            .order_by(Task.critical, Task.urgent, Task.created_at)
        )
        return list(result.scalars().all())

    async def list_by_agent(self, agent_id: UUID) -> list[Task]:
        """List tasks assigned to an agent."""
        result = await self.session.execute(
            select(Task)
            .where(Task.assigned_agent_id == agent_id)
            .order_by(Task.critical, Task.urgent, Task.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: UUID,
        data: TaskCreate,
        created_by_id: UUID | None = None,
    ) -> Task:
        """Create a new task."""
        validate_status(data.status)

        task = Task(
            project_id=project_id,
            title=data.title,
            description=data.description,
            status=data.status,
            critical=data.critical,
            urgent=data.urgent,
            module_path=data.module_path,
            parent_task_id=data.parent_task_id,
            created_by_id=created_by_id,
        )
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)

        # Broadcast task creation
        await self.ws_manager.broadcast_task_created(task)

        return task

    async def update(self, task_id: UUID, data: TaskUpdate) -> Task:
        """Update a task."""
        task = await self.get(task_id)

        # Validate status transition if status is being changed
        if data.status is not None and data.status != task.status:
            if not validate_transition(task.status, data.status):
                raise InvalidTaskStatus(
                    f"Cannot transition from '{task.status}' to '{data.status}'"
                )

        # Validate assigned agent exists if being changed
        if data.assigned_agent_id is not None:
            result = await self.session.execute(
                select(Agent).where(Agent.id == data.assigned_agent_id)
            )
            if not result.scalar_one_or_none():
                raise AgentNotFoundError(data.assigned_agent_id)

        # Apply updates
        update_fields = data.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            setattr(task, field, value)

        await self.session.flush()
        await self.session.refresh(task)

        # Broadcast task update
        await self.ws_manager.broadcast_task_update(task)

        return task

    async def update_status(self, task_id: UUID, new_status: str) -> Task:
        """Update only the status of a task."""
        task = await self.get(task_id)

        if not validate_transition(task.status, new_status):
            raise InvalidTaskStatus(
                f"Cannot transition from '{task.status}' to '{new_status}'"
            )

        task.status = new_status
        await self.session.flush()
        await self.session.refresh(task)

        # Broadcast task update
        await self.ws_manager.broadcast_task_update(task)

        return task

    async def assign(self, task_id: UUID, agent_id: UUID) -> Task:
        """Assign a task to an agent."""
        task = await self.get(task_id)
        previous_agent_id = task.assigned_agent_id

        # Validate agent exists
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise AgentNotFoundError(agent_id)

        task.assigned_agent_id = agent_id
        agent.current_task_id = task.id

        if previous_agent_id and previous_agent_id != agent_id:
            await self.session.execute(
                update(Agent)
                .where(
                    Agent.id == previous_agent_id,
                    Agent.current_task_id == task.id,
                )
                .values(current_task_id=None)
            )

        # Auto-transition to assigned if in backlog or specifying
        if task.status in ("backlog", "specifying"):
            task.status = "assigned"

        await self._wake_agent_for_assignment(agent)
        await self.session.flush()
        await self.session.refresh(task)

        # Broadcast task update
        await self.ws_manager.broadcast_task_update(task)

        return task

    async def _wake_agent_for_assignment(self, agent: Agent) -> None:
        """Ensure assigned agent is awake and has a sandbox ready."""
        prev_status = agent.status
        prev_sandbox_id = agent.sandbox_id
        await self.orchestrator.wake_agent(self.session, agent)
        if agent.status != prev_status or agent.sandbox_id != prev_sandbox_id:
            await self.ws_manager.broadcast_agent_status(agent)

    async def delete(self, task_id: UUID) -> bool:
        """Delete a task."""
        task = await self.get(task_id)
        await self.session.execute(
            update(Agent)
            .where(Agent.current_task_id == task.id)
            .values(current_task_id=None)
        )
        await self.session.delete(task)
        await self.session.flush()
        return True


def get_task_service(session: AsyncSession) -> TaskService:
    """Factory function to create TaskService instance."""
    return TaskService(session)
