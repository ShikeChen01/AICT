"""
Projects REST API endpoints.

List, create, import, and delete projects.
"""

import logging
import shutil
import subprocess
import uuid as uuid_module
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import verify_token
from backend.core.exceptions import ProjectNotFoundError
from backend.db.models import Agent, Project
from backend.db.session import get_db
from backend.schemas.project import ProjectCreate, ProjectImport, ProjectResponse, ProjectUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_response(project: Project) -> dict:
    """Convert Project model to response dict with git_token_set flag."""
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "spec_repo_path": project.spec_repo_path,
        "code_repo_url": project.code_repo_url,
        "code_repo_path": project.code_repo_path,
        "git_token_set": bool(project.git_token),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    projects = list(result.scalars().all())
    return [_project_to_response(p) for p in projects]


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
    return _project_to_response(project)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a new blank project."""
    project_id = uuid_module.uuid4()
    spec_path = Path(settings.spec_repo_path) / str(project_id)
    code_path = Path(settings.code_repo_path) / str(project_id)

    # Create directories
    spec_path.mkdir(parents=True, exist_ok=True)
    code_path.mkdir(parents=True, exist_ok=True)

    project = Project(
        id=project_id,
        name=data.name,
        description=data.description,
        spec_repo_path=str(spec_path),
        code_repo_url=data.code_repo_url or "",
        code_repo_path=str(code_path),
    )
    db.add(project)

    # Create default agents (Manager + OM)
    manager = Agent(
        project_id=project_id,
        role="manager",
        display_name="Manager",
        model=settings.claude_model,
        status="sleeping",
        priority=0,
        sandbox_persist=True,
    )
    om = Agent(
        project_id=project_id,
        role="om",
        display_name="Operations Manager",
        model=settings.gemini_model,
        status="sleeping",
        priority=1,
        sandbox_persist=True,
    )
    db.add(manager)
    db.add(om)

    await db.commit()
    await db.refresh(project)
    logger.info(f"Created project: {project.id} ({project.name})")
    return _project_to_response(project)


@router.post("/import", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def import_project(
    data: ProjectImport,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Import an existing Git repository as a new project."""
    project_id = uuid_module.uuid4()
    spec_path = Path(settings.spec_repo_path) / str(project_id)
    code_path = Path(settings.code_repo_path) / str(project_id)

    # Create spec directory
    spec_path.mkdir(parents=True, exist_ok=True)

    # Clone the repository
    clone_url = data.code_repo_url
    if data.git_token and "github.com" in clone_url:
        # Inject token for private repos: https://TOKEN@github.com/...
        clone_url = clone_url.replace("https://", f"https://{data.git_token}@")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(code_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        logger.info(f"Cloned repository for project {project_id}")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        logger.error(f"Failed to clone repository: {stderr}")
        # Clean up
        shutil.rmtree(spec_path, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to clone repository: {stderr or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(spec_path, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Repository clone timed out",
        )

    project = Project(
        id=project_id,
        name=data.name,
        description=data.description,
        spec_repo_path=str(spec_path),
        code_repo_url=data.code_repo_url,
        code_repo_path=str(code_path),
        git_token=data.git_token,
    )
    db.add(project)

    # Create default agents (Manager + OM)
    manager = Agent(
        project_id=project_id,
        role="manager",
        display_name="Manager",
        model=settings.claude_model,
        status="sleeping",
        priority=0,
        sandbox_persist=True,
    )
    om = Agent(
        project_id=project_id,
        role="om",
        display_name="Operations Manager",
        model=settings.gemini_model,
        status="sleeping",
        priority=1,
        sandbox_persist=True,
    )
    db.add(manager)
    db.add(om)

    await db.commit()
    await db.refresh(project)
    logger.info(f"Imported project: {project.id} ({project.name}) from {data.code_repo_url}")
    return _project_to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Update project details (name, description, git_token)."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ProjectNotFoundError(project_id)

    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.code_repo_url is not None:
        project.code_repo_url = data.code_repo_url
    if data.git_token is not None:
        project.git_token = data.git_token

    await db.commit()
    await db.refresh(project)
    return _project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and all associated data."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ProjectNotFoundError(project_id)

    # Clean up file system (optional, be careful in production)
    spec_path = Path(project.spec_repo_path)
    code_path = Path(project.code_repo_path)
    if spec_path.exists():
        shutil.rmtree(spec_path, ignore_errors=True)
    if code_path.exists():
        shutil.rmtree(code_path, ignore_errors=True)

    # Delete from database (cascades to agents, tasks, tickets, etc.)
    await db.delete(project)
    await db.commit()
    logger.info(f"Deleted project: {project_id}")
    return None
