"""
Projects REST API endpoints.

List and retrieve project information.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.core.exceptions import ProjectNotFoundError
from backend.db.models import Project
from backend.db.session import get_db
from backend.schemas.project import ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ProjectNotFoundError(project_id)
    return project
