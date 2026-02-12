"""
Internal Task API endpoints for agent tool calls.

These endpoints are called by agents to interact with the task system.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.core.access_control import enforce_kanban_write
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent
from backend.db.session import get_db
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from backend.services.task_service import get_task_service
from sqlalchemy import select

router = APIRouter(prefix="/tasks", tags=["internal-tasks"])


async def _get_agent_role(db: AsyncSession, agent_id: str) -> str:
    """Get the role of an agent by ID."""
    result = await db.execute(
        select(Agent).where(Agent.id == UUID(agent_id))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise AgentNotFoundError(agent_id)
    return agent.role


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    project_id: UUID = Query(..., description="Project ID"),
    status: str | None = Query(None, description="Filter by status"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a project. All agents can read."""
    service = get_task_service(db)
    if status:
        return await service.list_by_status(project_id, status)
    return await service.list_by_project(project_id)


@router.get("/mine", response_model=list[TaskResponse])
async def list_my_tasks(
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """List tasks assigned to the requesting agent."""
    service = get_task_service(db)
    return await service.list_by_agent(UUID(agent_id))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task. All agents can read."""
    service = get_task_service(db)
    return await service.get(task_id)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    project_id: UUID = Query(..., description="Project ID"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Create a task. Only GM and OM can create tasks."""
    role = await _get_agent_role(db, agent_id)
    enforce_kanban_write(role)

    service = get_task_service(db)
    return await service.create(project_id, data, UUID(agent_id))


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Update a task. Only GM and OM can update tasks (except status for engineers)."""
    role = await _get_agent_role(db, agent_id)
    enforce_kanban_write(role)

    service = get_task_service(db)
    return await service.update(task_id, data)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status: str = Query(..., description="New status"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """
    Update task status.
    
    Engineers can update status of their assigned tasks.
    GM and OM can update any task status.
    """
    role = await _get_agent_role(db, agent_id)
    service = get_task_service(db)

    # Engineers can only update their own tasks
    if role == "engineer":
        task = await service.get(task_id)
        if str(task.assigned_agent_id) != agent_id:
            raise AgentNotFoundError("Engineers can only update their assigned tasks")

    return await service.update_status(task_id, status)
