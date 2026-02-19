"""Internal task contract endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.access_control import enforce_kanban_write
from backend.core.auth import verify_agent_request
from backend.core.constants import USER_AGENT_ID
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent
from backend.db.session import get_db
from backend.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from backend.services.message_service import get_message_service
from backend.services.task_service import get_task_service

router = APIRouter(prefix="/tasks", tags=["internal-tasks"])


class AssignTaskRequest(BaseModel):
    agent_id: UUID
    target_agent_id: UUID


class AbortTaskRequest(BaseModel):
    agent_id: UUID
    reason: str = Field(..., min_length=1)


async def _get_agent(db: AsyncSession, agent_id: UUID) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise AgentNotFoundError(str(agent_id))
    return agent


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    project_id: UUID = Query(..., description="Project ID"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    actor = await _get_agent(db, UUID(agent_id))
    if actor.role != "manager":
        raise HTTPException(status_code=403, detail="Only manager can create tasks")
    service = get_task_service(db)
    return await service.create(project_id, data, UUID(agent_id))


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    project_id: UUID = Query(..., description="Project ID"),
    status: str | None = Query(None, description="Filter by status"),
    assigned_to: UUID | None = Query(None, description="Assigned agent"),
    _agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    service = get_task_service(db)
    if assigned_to:
        return await service.list_by_agent(assigned_to)
    if status:
        return await service.list_by_status(project_id, status)
    return await service.list_by_project(project_id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    _agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    service = get_task_service(db)
    return await service.get(task_id)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: UUID,
    body: AssignTaskRequest,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    actor = await _get_agent(db, body.agent_id)
    if actor.role != "manager":
        raise HTTPException(status_code=403, detail="Only manager can assign tasks")
    service = get_task_service(db)
    return await service.assign(task_id, body.target_agent_id)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status: str = Query(..., description="New status"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    actor = await _get_agent(db, UUID(agent_id))
    service = get_task_service(db)
    if actor.role == "engineer":
        task = await service.get(task_id)
        if task.assigned_agent_id != actor.id:
            raise HTTPException(
                status_code=403,
                detail="Engineers can only update their own tasks",
            )
    elif actor.role != "manager":
        enforce_kanban_write(actor.role)
    return await service.update_status(task_id, status)


@router.post("/abort-task")
async def abort_task(
    body: AbortTaskRequest,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    actor = await _get_agent(db, body.agent_id)
    if actor.role != "engineer":
        raise HTTPException(status_code=403, detail="Only engineers can abort tasks")
    if actor.current_task_id is None:
        raise HTTPException(status_code=400, detail="No active task to abort")

    service = get_task_service(db)
    task = await service.update_status(actor.current_task_id, "aborted")
    actor.current_task_id = None

    if task.created_by_id:
        msg_service = get_message_service(db)
        await msg_service.send(
            from_agent_id=actor.id,
            target_agent_id=task.created_by_id,
            project_id=task.project_id,
            content=f"Task '{task.title}' aborted: {body.reason}",
            message_type="system",
        )
    else:
        msg_service = get_message_service(db)
        await msg_service.send(
            from_agent_id=actor.id,
            target_agent_id=USER_AGENT_ID,
            project_id=task.project_id,
            content=f"Task '{task.title}' aborted: {body.reason}",
            message_type="system",
        )

    await db.commit()
    return {"message": "Task aborted and session should end."}
