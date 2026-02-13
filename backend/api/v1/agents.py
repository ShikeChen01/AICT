"""
Agents REST API endpoints.

List and retrieve agent information. Spawn engineers (up to max_engineers).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent, Task, Ticket
from backend.db.session import get_db
from backend.schemas.agent import (
    AgentResponse,
    AgentStatusWithQueueResponse,
    AgentTaskQueueItem,
    SpawnEngineerCreate,
)
from backend.services.agent_service import get_agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    project_id: UUID = Query(..., description="Project ID to list agents for"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List all agents for a project."""
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(Agent.priority, Agent.display_name)
    )
    return list(result.scalars().all())


@router.get("/status", response_model=list[AgentStatusWithQueueResponse])
async def list_agent_status(
    project_id: UUID = Query(..., description="Project ID to list agent status for"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    List agent status and queue details for a project.

    Queue includes non-done tasks currently assigned to each agent and open
    ticket counts where the agent is the recipient.
    """
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(Agent.priority, Agent.display_name)
    )
    agents = list(result.scalars().all())
    if not agents:
        return []

    agent_ids = [agent.id for agent in agents]

    tasks_result = await db.execute(
        select(Task)
        .where(
            Task.assigned_agent_id.in_(agent_ids),
            Task.status != "done",
        )
        .order_by(Task.assigned_agent_id, Task.critical, Task.urgent, Task.updated_at.desc())
    )
    tasks = list(tasks_result.scalars().all())
    tasks_by_agent: dict[UUID, list[AgentTaskQueueItem]] = {}
    for task in tasks:
        if task.assigned_agent_id is None:
            continue
        tasks_by_agent.setdefault(task.assigned_agent_id, []).append(
            AgentTaskQueueItem(
                id=task.id,
                title=task.title,
                status=task.status,
                critical=task.critical,
                urgent=task.urgent,
                module_path=task.module_path,
                updated_at=task.updated_at,
            )
        )

    ticket_counts_result = await db.execute(
        select(Ticket.to_agent_id, func.count(Ticket.id))
        .where(
            Ticket.to_agent_id.in_(agent_ids),
            Ticket.status == "open",
        )
        .group_by(Ticket.to_agent_id)
    )
    ticket_counts = {
        row[0]: int(row[1])
        for row in ticket_counts_result.all()
    }

    return [
        AgentStatusWithQueueResponse(
            id=agent.id,
            project_id=agent.project_id,
            role=agent.role,
            display_name=agent.display_name,
            model=agent.model,
            status=agent.status,
            current_task_id=agent.current_task_id,
            sandbox_id=agent.sandbox_id,
            sandbox_persist=bool(agent.sandbox_persist),
            priority=agent.priority,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            queue_size=len(tasks_by_agent.get(agent.id, [])),
            open_ticket_count=ticket_counts.get(agent.id, 0),
            task_queue=tasks_by_agent.get(agent.id, []),
        )
        for agent in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent by ID."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise AgentNotFoundError(agent_id)
    return agent


@router.post("", response_model=AgentResponse)
async def spawn_engineer(
    data: SpawnEngineerCreate,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Spawn a new engineer agent for the project.

    Enforces max_engineers limit (default 5). Raises 400 if limit reached.
    """
    service = get_agent_service(db)
    agent = await service.spawn_engineer(
        data.project_id,
        display_name=data.display_name,
        model=data.model,
        module_path=data.module_path,
    )
    await db.commit()
    await db.refresh(agent)
    return agent
