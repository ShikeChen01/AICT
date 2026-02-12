"""
Agents REST API endpoints.

List and retrieve agent information.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.core.exceptions import AgentNotFoundError
from backend.db.models import Agent
from backend.db.session import get_db
from backend.schemas.agent import AgentResponse

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
