"""
Task management tools for LangGraph agents.
"""

import uuid
from langchain_core.tools import tool
from backend.db.session import AsyncSessionLocal
from backend.services.task_service import TaskService
from backend.schemas.task import TaskCreate

@tool
async def create_kanban_task(title: str, description: str, project_id: str, critical: int = 5, urgent: int = 5) -> str:
    """
    Create a new task on the Kanban board.
    
    Args:
        title: Task title.
        description: Detailed task description.
        project_id: The UUID of the project.
        critical: Criticality (0-10, 0 is most critical).
        urgent: Urgency (0-10, 0 is most urgent).
    """
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        task = await service.create(
            project_id=uuid.UUID(project_id),
            data=TaskCreate(
                title=title,
                description=description,
                status="backlog",
                critical=critical,
                urgent=urgent
            )
        )
        await session.commit()
        return f"Task Created: {task.id} - {task.title}"

@tool
async def list_tasks(project_id: str, status: str = None) -> str:
    """
    List tasks for a project, optionally filtered by status.
    
    Args:
        project_id: The UUID of the project.
        status: Optional status filter (e.g., 'backlog', 'in_progress').
    """
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        if status:
            tasks = await service.list_by_status(uuid.UUID(project_id), status)
        else:
            tasks = await service.list_by_project(uuid.UUID(project_id))
            
        if not tasks:
            return "No tasks found."
            
        return "\n".join([f"{t.id} | [{t.status}] | {t.title} | Agent: {t.assigned_agent_id}" for t in tasks])

@tool
async def assign_task(task_id: str, agent_id: str) -> str:
    """
    Assign a task to an agent.
    
    Args:
        task_id: UUID of the task.
        agent_id: UUID of the agent.
    """
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        try:
            task = await service.assign(uuid.UUID(task_id), uuid.UUID(agent_id))
            await session.commit()
            return f"Task {task.title} assigned to agent {agent_id}"
        except Exception as e:
            return f"Error assigning task: {str(e)}"


@tool
async def update_task_status(task_id: str, status: str) -> str:
    """
    Update the status of a task in the Kanban workflow.

    Args:
        task_id: UUID of the task.
        status: One of backlog/specifying/assigned/in_progress/in_review/done.
    """
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        try:
            task = await service.update_status(uuid.UUID(task_id), status)
            await session.commit()
            return f"Task status updated: {task.id} -> {task.status}"
        except Exception as e:
            return f"Error updating task status: {str(e)}"


@tool
async def get_task_details(task_id: str) -> str:
    """
    Get full details of a task including its ID, title, description, and status.
    Use this to get task context before assigning to an engineer.

    Args:
        task_id: UUID of the task.
    """
    async with AsyncSessionLocal() as session:
        service = TaskService(session)
        try:
            task = await service.get(uuid.UUID(task_id))
            if not task:
                return f"Task {task_id} not found."
            return (
                f"TASK_CONTEXT:\n"
                f"  id: {task.id}\n"
                f"  title: {task.title}\n"
                f"  description: {task.description or 'No description'}\n"
                f"  status: {task.status}\n"
                f"  assigned_agent_id: {task.assigned_agent_id or 'Unassigned'}\n"
                f"  git_branch: {task.git_branch or 'None'}\n"
                f"  pr_url: {task.pr_url or 'None'}"
            )
        except Exception as e:
            return f"Error getting task details: {str(e)}"
