"""Project secrets API — per-project secret tokens for agent use."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.config import settings
from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import User
from backend.db.repositories.project_secrets import ProjectSecretsRepository
from backend.db.session import get_db
from backend.schemas.project_secrets import (
    ProjectSecretResponse,
    ProjectSecretUpsert,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/repositories", tags=["project-secrets"])


@router.get("/{repository_id}/secrets", response_model=list[ProjectSecretResponse])
async def list_project_secrets(
    repository_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List secrets for a project (masked: id, name, hint only; never value)."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectSecretsRepository(db, encryption_key=settings.secret_encryption_key)
    secrets = await repo.list_for_project(repository_id)
    return [
        ProjectSecretResponse(id=s.id, name=s.name, hint=s.hint, created_at=s.created_at)
        for s in secrets
    ]


@router.post(
    "/{repository_id}/secrets",
    response_model=ProjectSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_project_secret(
    repository_id: UUID,
    data: ProjectSecretUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a secret by name."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectSecretsRepository(db, encryption_key=settings.secret_encryption_key)
    secret = await repo.upsert(repository_id, data.name, data.value)
    await db.commit()
    await db.refresh(secret)
    return ProjectSecretResponse(
        id=secret.id, name=secret.name, hint=secret.hint, created_at=secret.created_at
    )


@router.delete("/{repository_id}/secrets/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_secret(
    repository_id: UUID,
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a secret by name."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectSecretsRepository(db, encryption_key=settings.secret_encryption_key)
    deleted = await repo.delete_by_name(repository_id, name)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )
    await db.commit()
