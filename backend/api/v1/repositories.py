"""Repository REST API endpoints."""

import shutil
import subprocess
import uuid as uuid_module
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import get_current_user
from backend.core.exceptions import ProjectNotFoundError
from backend.db.models import Agent, Repository, User
from backend.db.session import get_db
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.logging.my_logger import get_logger
from backend.schemas.project_settings import (
    ProjectSettingsResponse,
    ProjectSettingsUpdate,
)
from backend.schemas.repository import (
    RepositoryCreate,
    RepositoryImport,
    RepositoryResponse,
    RepositoryUpdate,
)
from backend.services.git_service import GitService

logger = get_logger(__name__)

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _repository_to_response(repository: Repository) -> dict:
    return {
        "id": repository.id,
        "owner_id": repository.owner_id,
        "name": repository.name,
        "description": repository.description,
        "spec_repo_path": repository.spec_repo_path,
        "code_repo_url": repository.code_repo_url,
        "code_repo_path": repository.code_repo_path,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
    }


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository)
        .where(
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            )
        )
        .order_by(Repository.created_at.desc())
    )
    repositories = list(result.scalars().all())
    return [_repository_to_response(r) for r in repositories]


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            ),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise ProjectNotFoundError(repository_id)
    return _repository_to_response(repository)


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    data: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure a GitHub token in user settings before creating repositories.",
        )

    repository_id = uuid_module.uuid4()
    spec_path = Path(settings.spec_repo_path) / str(repository_id)
    code_path = Path(settings.code_repo_path) / str(repository_id)

    spec_path.mkdir(parents=True, exist_ok=True)
    code_path.mkdir(parents=True, exist_ok=True)

    git_service = GitService(repo_path=str(code_path), github_token=current_user.github_token)
    github_repo = git_service.create_repository(
        name=data.name,
        description=data.description or "",
        private=data.private,
    )
    code_repo_url = github_repo.get("clone_url") or github_repo.get("html_url") or ""

    clone_url = code_repo_url
    if current_user.github_token and "github.com" in code_repo_url:
        clone_url = code_repo_url.replace("https://", f"https://{current_user.github_token}@")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(code_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(spec_path, ignore_errors=True)
        shutil.rmtree(code_path, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to clone repository: {(exc.stderr or exc.stdout or 'unknown error').strip()}",
        ) from exc

    repository = Repository(
        id=repository_id,
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
        spec_repo_path=str(spec_path),
        code_repo_url=code_repo_url,
        code_repo_path=str(code_path),
    )
    db.add(repository)

    manager = Agent(
        project_id=repository_id,
        role="manager",
        display_name="Manager",
        model=settings.manager_model_default,
        status="sleeping",
        sandbox_persist=True,
    )
    cto = Agent(
        project_id=repository_id,
        role="cto",
        display_name="CTO",
        model=settings.cto_model_default,
        status="sleeping",
        sandbox_persist=True,
    )
    db.add(manager)
    db.add(cto)

    await db.commit()
    await db.refresh(repository)
    logger.info("Created repository: %s (%s)", repository.id, repository.name)
    return _repository_to_response(repository)


@router.post("/import", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def import_repository(
    data: RepositoryImport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository_id = uuid_module.uuid4()
    spec_path = Path(settings.spec_repo_path) / str(repository_id)
    code_path = Path(settings.code_repo_path) / str(repository_id)
    spec_path.mkdir(parents=True, exist_ok=True)

    clone_url = data.code_repo_url
    if current_user.github_token and "github.com" in clone_url:
        clone_url = clone_url.replace("https://", f"https://{current_user.github_token}@")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(code_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        shutil.rmtree(spec_path, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to clone repository: {stderr or 'unknown error'}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(spec_path, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Repository clone timed out",
        ) from exc

    repository = Repository(
        id=repository_id,
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
        spec_repo_path=str(spec_path),
        code_repo_url=data.code_repo_url,
        code_repo_path=str(code_path),
    )
    db.add(repository)

    manager = Agent(
        project_id=repository_id,
        role="manager",
        display_name="Manager",
        model=settings.manager_model_default,
        status="sleeping",
        sandbox_persist=True,
    )
    cto = Agent(
        project_id=repository_id,
        role="cto",
        display_name="CTO",
        model=settings.cto_model_default,
        status="sleeping",
        sandbox_persist=True,
    )
    db.add(manager)
    db.add(cto)

    await db.commit()
    await db.refresh(repository)
    return _repository_to_response(repository)


@router.patch("/{repository_id}", response_model=RepositoryResponse)
async def update_repository(
    repository_id: UUID,
    data: RepositoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            ),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise ProjectNotFoundError(repository_id)

    if data.name is not None:
        repository.name = data.name
    if data.description is not None:
        repository.description = data.description
    if data.code_repo_url is not None:
        repository.code_repo_url = data.code_repo_url

    await db.commit()
    await db.refresh(repository)
    return _repository_to_response(repository)


@router.get("/{repository_id}/settings", response_model=ProjectSettingsResponse)
async def get_repository_settings(
    repository_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project settings for a repository."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            ),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise ProjectNotFoundError(repository_id)
    repo_settings = ProjectSettingsRepository(db)
    settings = await repo_settings.get_or_create_defaults(repository_id)
    await db.commit()
    await db.refresh(settings)
    return ProjectSettingsResponse.model_validate(settings)


@router.patch("/{repository_id}/settings", response_model=ProjectSettingsResponse)
async def update_repository_settings(
    repository_id: UUID,
    data: ProjectSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project settings."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            ),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise ProjectNotFoundError(repository_id)
    repo_settings = ProjectSettingsRepository(db)
    settings = await repo_settings.get_or_create_defaults(repository_id)
    if data.max_engineers is not None:
        settings.max_engineers = data.max_engineers
    if data.persistent_sandbox_count is not None:
        settings.persistent_sandbox_count = data.persistent_sandbox_count
    await db.commit()
    await db.refresh(settings)
    return ProjectSettingsResponse.model_validate(settings)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            or_(
                Repository.owner_id == current_user.id,
                Repository.owner_id.is_(None),
            ),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise ProjectNotFoundError(repository_id)

    spec_path = Path(repository.spec_repo_path)
    code_path = Path(repository.code_repo_path)
    if spec_path.exists():
        shutil.rmtree(spec_path, ignore_errors=True)
    if code_path.exists():
        shutil.rmtree(code_path, ignore_errors=True)

    # Break Agent <-> Task cross references before cascading delete.
    await db.execute(
        update(Agent)
        .where(Agent.project_id == repository_id)
        .values(current_task_id=None)
    )

    await db.delete(repository)
    await db.commit()
    return None
