"""
Agents REST API endpoints.

List and retrieve agent information. Spawn engineers (up to max_engineers).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.exceptions import AgentNotFoundError
from backend.core.project_access import require_project_access
from backend.db.models import Agent, Task, User
from backend.db.session import get_db
from backend.schemas.agent import (
    AgentContextResponse,
    AgentResponse,
    AgentStatusWithQueueResponse,
    AgentTaskQueueItem,
    AgentTool,
    SpawnEngineerCreate,
)
from backend.services.agent_service import get_agent_service
from backend.services.message_service import get_message_service

router = APIRouter(prefix="/agents", tags=["agents"])


async def _ensure_agent_access(db: AsyncSession, agent_id: UUID, user_id: UUID) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise AgentNotFoundError(agent_id)
    await require_project_access(db, agent.project_id, user_id)
    return agent


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    project_id: UUID = Query(..., description="Project ID to list agents for"),
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents for a project (ordered by role: manager, cto, engineer)."""
    if isinstance(current_user, User):
        await require_project_access(db, project_id, current_user.id)
    role_order = case(
        (Agent.role == "manager", 0),
        (Agent.role == "cto", 1),
        (Agent.role == "engineer", 2),
        else_=3,
    )
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(role_order, Agent.display_name)
    )
    return list(result.scalars().all())


@router.get("/status", response_model=list[AgentStatusWithQueueResponse])
async def list_agent_status(
    project_id: UUID = Query(..., description="Project ID to list agent status for"),
    current_user: User | None = Depends(get_current_user),
    _auth: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List agent status and queue details for a project.
    pending_message_count = unread (status=sent) channel messages for that agent.
    """
    if isinstance(current_user, User):
        await require_project_access(db, project_id, current_user.id)
    role_order = case(
        (Agent.role == "manager", 0),
        (Agent.role == "cto", 1),
        (Agent.role == "engineer", 2),
        else_=3,
    )
    result = await db.execute(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(role_order, Agent.display_name)
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

    msg_service = get_message_service(db)
    pending_counts = await msg_service.count_unread_by_targets(agent_ids)

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
            memory=agent.memory,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            queue_size=len(tasks_by_agent.get(agent.id, [])),
            pending_message_count=pending_counts.get(agent.id, 0),
            task_queue=tasks_by_agent.get(agent.id, []),
        )
        for agent in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent by ID."""
    agent = await _ensure_agent_access(db, agent_id, current_user.id)
    return agent


@router.post("", response_model=AgentResponse)
async def spawn_engineer(
    data: SpawnEngineerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Spawn a new engineer agent for the project.

    Enforces max_engineers limit (default 5). Raises 400 if limit reached.
    """
    await require_project_access(db, data.project_id, current_user.id)
    service = get_agent_service(db)
    agent = await service.spawn_engineer(
        data.project_id,
        display_name=data.display_name,
        seniority=data.seniority,
        module_path=data.module_path,
    )
    await db.commit()
    await db.refresh(agent)
    return agent


# ── Agent Inspector (Frontend V2) ──────────────────────────────────


# System prompts for different roles (used by the graph nodes and inspector)
_SYSTEM_PROMPTS = {
    "manager": """You are the Manager (GM) agent in an AI software development team.
Your responsibilities:
- Communicate with the user to understand requirements
- Break down high-level goals into actionable tasks and assign/dispatch to engineers
- Consult the CTO for architecture and design when needed
- Review completed work and provide feedback to the user""",
    "cto": """You are the CTO (Chief Technology Officer) in an AI software development team.
Your responsibilities:
- Provide architectural guidance and design recommendations when consulted
- Review technical decisions and integration concerns
- You do NOT assign tasks or dispatch work to engineers; the Manager does that""",
    "engineer": """You are an Engineer in an AI software development team.
Your responsibilities:
- Implement specific coding tasks assigned by the Manager
- Write clean, tested code following project conventions
- Create branches, commits, and pull requests
- Report completion or ask the Manager or CTO for help when stuck""",
}


def _get_tools_for_role(role: str) -> list[AgentTool]:
    """Return the list of tools available to an agent role."""
    from backend.tools.registry import get_manager_tools, get_cto_tools, get_engineer_tools

    tool_map = {
        "manager": get_manager_tools,
        "cto": get_cto_tools,
        "engineer": get_engineer_tools,
    }
    getter = tool_map.get(role)
    if not getter:
        return []

    tools = getter()
    return [
        AgentTool(name=t.name, description=getattr(t, "description", None))
        for t in tools
    ]


class AgentMemoryResponse(BaseModel):
    """Response for GET agents/{id}/memory."""

    memory: dict | None


@router.get("/{agent_id}/memory", response_model=AgentMemoryResponse)
async def get_agent_memory(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the agent's Layer 1 memory (self-define block content)."""
    agent = await _ensure_agent_access(db, agent_id, current_user.id)
    return AgentMemoryResponse(memory=agent.memory)


class InterruptResponse(BaseModel):
    message: str = "Agent interrupted."


class WakeResponse(BaseModel):
    message: str = "Agent woken."


class InterruptRequest(BaseModel):
    reason: str


class WakeRequest(BaseModel):
    message: str | None = None


@router.post("/{agent_id}/interrupt", response_model=InterruptResponse)
async def interrupt_agent(
    agent_id: UUID,
    body: InterruptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force-end the agent's current session (user action). Same as interrupt_agent tool."""
    await _ensure_agent_access(db, agent_id, current_user.id)
    from backend.workers.worker_manager import get_worker_manager

    get_worker_manager().interrupt_agent(agent_id)
    return InterruptResponse()


@router.post("/{agent_id}/wake", response_model=WakeResponse)
async def wake_agent(
    agent_id: UUID,
    body: WakeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a wake-up notification to a sleeping agent. Optionally include a message."""
    agent = await _ensure_agent_access(db, agent_id, current_user.id)
    if body.message:
        from backend.services.message_service import get_message_service
        from backend.core.constants import USER_AGENT_ID

        service = get_message_service(db)
        await service.send(
            from_agent_id=USER_AGENT_ID,
            target_agent_id=agent.id,
            project_id=agent.project_id,
            content=body.message,
        )
        await db.commit()
    from backend.workers.message_router import get_message_router

    get_message_router().notify(agent_id)
    return WakeResponse()


@router.get("/{agent_id}/context", response_model=AgentContextResponse)
async def get_agent_context(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get agent context for the Inspector panel.

    Returns system prompt, available tools, and recent message history.
    """
    agent = await _ensure_agent_access(db, agent_id, current_user.id)

    # Get system prompt for this role
    system_prompt = _SYSTEM_PROMPTS.get(agent.role, "")

    # Get available tools
    available_tools = _get_tools_for_role(agent.role)

    # Recent messages would come from LangGraph checkpointer
    # For now, return empty list (implement when checkpointer integration is done)
    recent_messages: list[dict] = []

    return AgentContextResponse(
        id=agent.id,
        role=agent.role,
        display_name=agent.display_name,
        tier=agent.tier,
        model=agent.model,
        status=agent.status,
        system_prompt=system_prompt,
        available_tools=available_tools,
        recent_messages=recent_messages,
        sandbox_id=agent.sandbox_id,
        sandbox_active=bool(agent.sandbox_id),
    )
