"""
Task REST API endpoints.

CRUD operations for Kanban tasks.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.exceptions import ProjectNotFoundError
from backend.db.models import Repository, Task, User
from backend.db.session import get_db
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from backend.services.task_service import get_task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _ensure_project_access(db: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    result = await db.execute(
        select(Repository).where(
            Repository.id == project_id,
            (Repository.owner_id == user_id) | (Repository.owner_id.is_(None)),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")


async def _ensure_task_access(db: AsyncSession, task_id: UUID, user_id: UUID) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await _ensure_project_access(db, task.project_id, user_id)
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    project_id: UUID = Query(..., description="Project ID to list tasks for"),
    status: str | None = Query(None, description="Filter by status"),
    agent_id: UUID | None = Query(None, description="Filter by assigned agent"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a project with optional filters."""
    await _ensure_project_access(db, project_id, current_user.id)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task by ID."""
    await _ensure_task_access(db, task_id, current_user.id)
    service = get_task_service(db)
    return await service.get(task_id)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    project_id: UUID = Query(..., description="Project ID to create task in"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task."""
    await _ensure_project_access(db, project_id, current_user.id)
    service = get_task_service(db)
    return await service.create(project_id, data)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a task."""
    await _ensure_task_access(db, task_id, current_user.id)
    service = get_task_service(db)
    return await service.update(task_id, data)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status: str = Query(..., description="New status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update only the status of a task."""
    await _ensure_task_access(db, task_id, current_user.id)
    service = get_task_service(db)
    return await service.update_status(task_id, status)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: UUID,
    agent_id: UUID = Query(..., description="Agent ID to assign"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a task to an agent."""
    await _ensure_task_access(db, task_id, current_user.id)
    service = get_task_service(db)
    return await service.assign(task_id, agent_id)


@router.post("/{task_id}/move", response_model=TaskResponse)
async def move_task(
    task_id: UUID,
    new_project_id: UUID = Query(..., description="Destination project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move a task to a different project."""
    await _ensure_task_access(db, task_id, current_user.id)
    await _ensure_project_access(db, new_project_id, current_user.id)
    service = get_task_service(db)
    try:
        return await service.move_to_project(task_id, new_project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Destination project not found")


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task."""
    await _ensure_task_access(db, task_id, current_user.id)
    service = get_task_service(db)
    await service.delete(task_id)
    return None
