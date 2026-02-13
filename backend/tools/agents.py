"""
Agent management tools for LangGraph agents.
"""

import uuid
from langchain_core.tools import tool

from backend.core.exceptions import MaxEngineersReached
from backend.db.session import AsyncSessionLocal
from backend.services.agent_service import get_agent_service


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
