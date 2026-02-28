"""Architecture document REST endpoints — read-only for users."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import User
from backend.db.repositories.project_documents import ProjectDocumentRepository
from backend.db.session import get_db
from backend.schemas.project_documents import (
    ProjectDocumentResponse,
    ProjectDocumentSummaryResponse,
)

router = APIRouter(prefix="/repositories", tags=["documents"])


@router.get(
    "/{repository_id}/documents",
    response_model=list[ProjectDocumentSummaryResponse],
)
async def list_documents(
    repository_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all architecture documents for a project (content excluded)."""
    await require_project_access(db, current_user.id, repository_id)
    repo = ProjectDocumentRepository(db)
    docs = await repo.list_by_project(repository_id)
    return [ProjectDocumentSummaryResponse.model_validate(d) for d in docs]


@router.get(
    "/{repository_id}/documents/{doc_type:path}",
    response_model=ProjectDocumentResponse,
)
async def get_document(
    repository_id: UUID,
    doc_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single architecture document with full Markdown content."""
    await require_project_access(db, current_user.id, repository_id)
    repo = ProjectDocumentRepository(db)
    doc = await repo.get_by_type(repository_id, doc_type)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_type}' not found.")
    return ProjectDocumentResponse.model_validate(doc)
