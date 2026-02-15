"""
Agent management tools for LangGraph agents.
"""

import uuid
from langchain_core.tools import tool

from backend.core.exceptions import MaxEngineersReached
from backend.db.models import EngineerJob, Agent, Task
from backend.db.session import AsyncSessionLocal
from backend.services.agent_service import get_agent_service
from sqlalchemy import select


@tool
async def spawn_engineer(
    project_id: str,
    display_name: str | None = None,
    model: str = "claude-4.5",
) -> str:
    """
    Spawn a new engineer agent for the project.

    Use this when you need to assign work to an engineer but there are not
    enough engineers yet. Maximum 5 engineers per project.

    Args:
        project_id: The UUID of the project.
        display_name: Optional display name (e.g. Engineer-3). Auto-generated if omitted.
        model: Model to use for the engineer.
    """
    async with AsyncSessionLocal() as session:
        service = get_agent_service(session)
        try:
            agent = await service.spawn_engineer(
                uuid.UUID(project_id),
                display_name=display_name,
                model=model,
            )
            await session.commit()
            return (
                f"Engineer spawned: {agent.display_name} (id={agent.id}). "
                f"You can now assign tasks to this agent."
            )
        except MaxEngineersReached as e:
            return str(e)


@tool
async def list_engineers(project_id: str) -> str:
    """
    List all engineer agents for a project.
    
    Use this to find available engineers to assign tasks to.

    Args:
        project_id: The UUID of the project.
    """
    async with AsyncSessionLocal() as session:
        service = get_agent_service(session)
        engineers = await service.list_by_role(uuid.UUID(project_id), "engineer")
        
        if not engineers:
            return "No engineers found for this project. Use spawn_engineer to create one."
        
        lines = ["Available Engineers:"]
        for eng in engineers:
            status_indicator = "BUSY" if eng.status == "busy" else "AVAILABLE"
            task_info = f" (task: {eng.current_task_id})" if eng.current_task_id else ""
            lines.append(
                f"  - {eng.display_name} (id={eng.id}) [{status_indicator}]{task_info}"
            )
        return "\n".join(lines)


@tool
async def dispatch_to_engineer(task_id: str, agent_id: str) -> str:
    """
    Dispatch a task to an engineer for background execution.
    
    The engineer will work on this task asynchronously and report results
    via WebSocket updates and tickets. This returns immediately without
    waiting for the engineer to complete.
    
    Use this after assigning a task to an engineer to kick off their work.
    
    Args:
        task_id: The UUID of the task to work on.
        agent_id: The UUID of the engineer agent to assign.
    
    Returns:
        Confirmation message with job ID, or error description.
    """
    async with AsyncSessionLocal() as session:
        try:
            task_uuid = uuid.UUID(task_id)
            agent_uuid = uuid.UUID(agent_id)
        except ValueError as e:
            return f"Invalid UUID format: {e}"
        
        # Verify agent exists and is an engineer
        result = await session.execute(
            select(Agent).where(Agent.id == agent_uuid)
        )
        agent = result.scalar_one_or_none()
        
        if not agent:
            return f"Engineer not found: {agent_id}"
        if agent.role != "engineer":
            return f"Agent {agent.display_name} is not an engineer (role: {agent.role})"
        
        # Verify task exists
        result = await session.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return f"Task not found: {task_id}"
        
        # Check if there's already a pending/running job for this task
        existing = await session.execute(
            select(EngineerJob).where(
                EngineerJob.task_id == task_uuid,
                EngineerJob.status.in_(["pending", "running"])
            )
        )
        existing_job = existing.scalar_one_or_none()
        if existing_job:
            return (
                f"Task already has an active job (id={existing_job.id}, "
                f"status={existing_job.status})"
            )
        
        # Create the job
        job = EngineerJob(
            project_id=agent.project_id,
            task_id=task_uuid,
            agent_id=agent_uuid,
            status="pending",
        )
        session.add(job)
        
        # Update task status to in_progress
        task.status = "in_progress"
        
        # Mark engineer as busy
        agent.status = "busy"
        agent.current_task_id = task_uuid
        
        await session.commit()
        
        return (
            f"DISPATCHED: Job {job.id} created.\n"
            f"Engineer {agent.display_name} will work on '{task.title}' in the background.\n"
            f"Check job status via WebSocket 'job_*' events or the /api/v1/jobs endpoint."
        )
