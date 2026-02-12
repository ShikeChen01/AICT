"""
Task REST API endpoints.

CRUD operations for Kanban tasks.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.db.session import get_db
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from backend.services.task_service import get_task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    project_id: UUID = Query(..., description="Project ID to list tasks for"),
    status: str | None = Query(None, description="Filter by status"),
    agent_id: UUID | None = Query(None, description="Filter by assigned agent"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a project with optional filters."""
    service = get_task_service(db)

    if agent_id:
        tasks = await service.list_by_agent(agent_id)
    elif status:
        tasks = await service.list_by_status(project_id, status)
    else:
        tasks = await service.list_by_project(project_id)

    return tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task by ID."""
    service = get_task_service(db)
    return await service.get(task_id)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    project_id: UUID = Query(..., description="Project ID to create task in"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task."""
    service = get_task_service(db)
    return await service.create(project_id, data)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Update a task."""
    service = get_task_service(db)
    return await service.update(task_id, data)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status: str = Query(..., description="New status"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Update only the status of a task."""
    service = get_task_service(db)
    return await service.update_status(task_id, status)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: UUID,
    agent_id: UUID = Query(..., description="Agent ID to assign"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Assign a task to an agent."""
    service = get_task_service(db)
    return await service.assign(task_id, agent_id)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task."""
    service = get_task_service(db)
    await service.delete(task_id)
    return None
