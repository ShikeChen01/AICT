"""
Agents REST API endpoints.

List and retrieve agent information. Spawn engineers (up to max_engineers).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.auth import get_current_user
from backend.core.exceptions import AgentNotFoundError
from backend.core.project_access import require_project_access
from backend.db.models import Agent, Repository, Task, User
from backend.db.repositories.agent_templates import PromptBlockConfigRepository
from backend.db.session import get_db
from backend.llm.model_resolver import infer_provider
from backend.llm.model_catalog import is_claude_model
from backend.schemas.agent import (
    AgentContextResponse,
    AgentResponse,
    AgentStatusWithQueueResponse,
    AgentTaskQueueItem,
    AgentTool,
    SpawnEngineerCreate,
    UpdateAgentRequest,
)
from backend.services.agent_service import get_agent_service
from backend.services.message_service import get_message_service

router = APIRouter(prefix="/agents", tags=["agents"])


async def _ensure_agent_access(db: AsyncSession, agent_id: UUID, user_id: UUID) -> Agent:
    result = await db.execute(
        select(Agent).options(selectinload(Agent.sandbox)).where(Agent.id == agent_id)
    )
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
    """List all agents for a project (ordered by display name)."""
    if isinstance(current_user, User):
        await require_project_access(db, project_id, current_user.id)
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.sandbox))
        .where(Agent.project_id == project_id)
        .order_by(Agent.created_at, Agent.display_name)
    )
    agents = list(result.scalars().all())

    # Manually construct responses to avoid accessing non-existent attributes
    responses = []
    for agent in agents:
        responses.append(AgentResponse(
            id=agent.id,
            project_id=agent.project_id,
            template_id=agent.template_id,
            role=agent.role,
            display_name=agent.display_name,
            model=agent.model,
            provider=agent.provider,
            thinking_enabled=agent.thinking_enabled,
            status=agent.status,
            current_task_id=agent.current_task_id,
            sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,
            memory=agent.memory,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        ))
    return responses


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
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.sandbox))
        .where(Agent.project_id == project_id)
        .order_by(Agent.created_at, Agent.display_name)
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
            sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,
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
    return AgentResponse(
        id=agent.id,
        project_id=agent.project_id,
        template_id=agent.template_id,
        role=agent.role,
        display_name=agent.display_name,
        model=agent.model,
        provider=agent.provider,
        thinking_enabled=agent.thinking_enabled,
        status=agent.status,
        current_task_id=agent.current_task_id,
        sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,
        memory=agent.memory,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("", response_model=AgentResponse)
async def create_agent(
    data: SpawnEngineerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent from a template.

    If template_id is provided, creates from that template.
    Otherwise falls back to the project's default worker template.
    No role-based limits — users manage their own agent fleet.
    """
    await require_project_access(db, data.project_id, current_user.id)
    service = get_agent_service(db)

    if data.template_id:
        agent = await service.create_agent(
            data.project_id,
            data.template_id,
            display_name=data.display_name,
        )
    else:
        # Backward compat: no template_id → use spawn_engineer path
        agent = await service.spawn_engineer(
            data.project_id,
            display_name=data.display_name,
            template_id=None,
        )

    await db.commit()
    await db.refresh(agent)
    return agent


# ── Agent Inspector (Frontend V2) ──────────────────────────────────


# Generic fallback prompt when no template/prompt blocks are configured
_DEFAULT_SYSTEM_PROMPT = """You are an AI agent in a software development team.
Your behavior, capabilities, and responsibilities are defined by your assigned
template and tools. Use the tools available to you to accomplish your tasks."""


def _get_tools_for_agent(agent_id, role: str, db) -> list[AgentTool]:
    """Return tools available to an agent (reads from DB config)."""
    # This is sync context (for inspector), so we use the role-based fallback
    from backend.tools.loop_registry import get_tool_defs_for_role

    return [
        AgentTool(name=t["name"], description=t.get("description"))
        for t in get_tool_defs_for_role(role)
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


class StopResponse(BaseModel):
    message: str = "Agent stopped."


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
    """Force-end the agent's current session (agent-to-agent action)."""
    await _ensure_agent_access(db, agent_id, current_user.id)
    from backend.workers.worker_manager import get_worker_manager

    get_worker_manager().interrupt_agent(agent_id)
    return InterruptResponse()


@router.post("/{agent_id}/stop", response_model=StopResponse)
async def stop_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Emergency stop: immediately halt the agent's running loop (user action).

    Interrupts the worker and broadcasts an agent_stopped WebSocket event so all
    connected clients update the agent's status without polling.
    """
    agent = await _ensure_agent_access(db, agent_id, current_user.id)
    from backend.websocket.manager import ws_manager
    from backend.workers.worker_manager import get_worker_manager

    get_worker_manager().interrupt_agent(agent_id)
    try:
        await ws_manager.broadcast_agent_stopped(
            project_id=agent.project_id,
            agent_id=agent.id,
            display_name=agent.display_name,
        )
    except Exception:
        pass
    return StopResponse()


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


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    body: UpdateAgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's model, provider, thinking_enabled, or display_name.

    These values are written directly to the agent row (write-through pattern).
    Changes take effect on the agent's next session.
    """
    agent = await _ensure_agent_access(db, agent_id, current_user.id)

    if body.model is not None:
        agent.model = body.model
        # Re-infer provider if not explicitly provided
        if body.provider is None:
            agent.provider = infer_provider(body.model)
    if body.provider is not None:
        agent.provider = body.provider
    if body.thinking_enabled is not None:
        agent.thinking_enabled = body.thinking_enabled
    if body.display_name is not None:
        agent.display_name = body.display_name
    if body.token_allocations is not None:
        # Empty dict resets to system defaults (NULL in DB)
        alloc = body.token_allocations if body.token_allocations else None
        if alloc and "max_images_per_turn" in alloc:
            # max_images_per_turn is only meaningful for Claude; validate range
            resolved_model = (body.model or agent.model or "")
            if not is_claude_model(resolved_model):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "max_images_per_turn is only configurable for Claude models. "
                        f"Model '{resolved_model}' uses the system default of 10 images."
                    ),
                )
            val = alloc["max_images_per_turn"]
            if not isinstance(val, int) or not (1 <= val <= 20):
                raise HTTPException(
                    status_code=422,
                    detail="max_images_per_turn must be an integer between 1 and 20.",
                )
        agent.token_allocations = alloc

    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}/context", response_model=AgentContextResponse)
async def get_agent_context(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent context for the Inspector panel.

    Returns the real assembled system prompt (from DB block configs),
    available tools, and recent message history.
    """
    from backend.prompts.assembly import PromptAssembly

    agent = await _ensure_agent_access(db, agent_id, current_user.id)

    # Load the project for placeholder resolution
    result = await db.execute(select(Repository).where(Repository.id == agent.project_id))
    project = result.scalar_one_or_none()

    # Assemble the real system prompt from DB block configs
    system_prompt: str | None = None
    if project:
        block_repo = PromptBlockConfigRepository(db)
        block_configs = await block_repo.list_for_agent(agent.id)
        if block_configs:
            memory_content = agent.memory
            if isinstance(memory_content, dict):
                import json
                memory_content = json.dumps(memory_content) if memory_content else None
            pa = PromptAssembly(
                agent, project, memory_content,
                block_configs=block_configs,
                thinking_stage=None,  # show base prompt (thinking OFF) in inspector
            )
            system_prompt = pa.system_prompt
        else:
            system_prompt = _DEFAULT_SYSTEM_PROMPT
    else:
        system_prompt = _DEFAULT_SYSTEM_PROMPT

    available_tools = _get_tools_for_agent(agent.id, agent.role, db)

    return AgentContextResponse(
        id=agent.id,
        project_id=agent.project_id,
        template_id=agent.template_id,
        role=agent.role,
        display_name=agent.display_name,
        model=agent.model,
        provider=agent.provider,
        thinking_enabled=agent.thinking_enabled,
        status=agent.status,
        system_prompt=system_prompt,
        available_tools=available_tools,
        recent_messages=[],
        sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,
        sandbox_active=bool(agent.sandbox),
    )


@router.delete("/{agent_id}", status_code=200)
async def delete_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an agent from the project. Any agent can be deleted."""
    agent = await _ensure_agent_access(db, agent_id, current_user.id)
    service = get_agent_service(db)
    try:
        agent = await service.remove_agent(agent_id, agent.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return {"ok": True, "message": f"Agent '{agent.display_name}' removed."}
