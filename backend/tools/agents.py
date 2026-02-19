"""
Agent management tools for LangGraph agents.
"""

import uuid
from langchain_core.tools import tool

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

from backend.core.exceptions import MaxEngineersReached
from backend.db.models import Agent
from backend.db.session import AsyncSessionLocal
from backend.services.agent_service import get_agent_service


@tool
async def spawn_engineer(
    project_id: str,
    display_name: str | None = None,
    seniority: str | None = None,
) -> str:
    """
    Spawn a new engineer agent for the project.

    Use this when you need to assign work to an engineer but there are not
    enough engineers yet. Maximum 5 engineers per project.

    Args:
        project_id: The UUID of the project.
        display_name: Optional display name (e.g. Engineer-3). Auto-generated if omitted.
        seniority: Optional engineer seniority (junior/intermediate/senior).
    """
    async with AsyncSessionLocal() as session:
        service = get_agent_service(session)
        try:
            agent = await service.spawn_engineer(
                uuid.UUID(project_id),
                display_name=display_name,
                seniority=seniority,
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
