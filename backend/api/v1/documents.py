"""Architecture document REST endpoints.

Users can read and directly edit documents. Every edit (by user or agent) creates
a version snapshot. Users can browse history and revert to any past version.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


# ── Schemas ────────────────────────────────────────────────────────────────────

class DocumentEditRequest(BaseModel):
    content: str = Field(..., description="Full markdown content of the document")
    title: str | None = Field(None, description="Optional display title")
    edit_summary: str | None = Field(None, max_length=255, description="Optional edit description")


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    content: str | None
    title: str | None
    edited_by_agent_id: UUID | None
    edited_by_user_id: UUID | None
    edit_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionSummaryResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    title: str | None
    edited_by_agent_id: UUID | None
    edited_by_user_id: UUID | None
    edit_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RevertRequest(BaseModel):
    version_number: int = Field(..., ge=1)


# ── Existing endpoints ─────────────────────────────────────────────────────────

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
    await require_project_access(db, repository_id, current_user.id)
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
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectDocumentRepository(db)
    doc = await repo.get_by_type(repository_id, doc_type)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_type}' not found.")
    return ProjectDocumentResponse.model_validate(doc)


# ── New user-edit and versioning endpoints ─────────────────────────────────────

@router.put(
    "/{repository_id}/documents/{doc_type:path}",
    response_model=ProjectDocumentResponse,
)
async def edit_document(
    repository_id: UUID,
    doc_type: str,
    body: DocumentEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User edits a document. Creates a version snapshot of the previous content."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectDocumentRepository(db)
    doc = await repo.user_edit(
        project_id=repository_id,
        doc_type=doc_type,
        content=body.content,
        user_id=current_user.id,
        title=body.title,
        edit_summary=body.edit_summary,
    )
    await db.commit()
    await db.refresh(doc)
    return ProjectDocumentResponse.model_validate(doc)


@router.get(
    "/{repository_id}/documents/{doc_type:path}/versions",
    response_model=list[DocumentVersionSummaryResponse],
)
async def list_document_versions(
    repository_id: UUID,
    doc_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List version history for a document (newest first, content excluded)."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectDocumentRepository(db)
    versions = await repo.list_versions(repository_id, doc_type)
    return versions


@router.get(
    "/{repository_id}/documents/{doc_type:path}/versions/{version_number:int}",
    response_model=DocumentVersionResponse,
)
async def get_document_version(
    repository_id: UUID,
    doc_type: str,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full content of a specific version."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectDocumentRepository(db)
    version = await repo.get_version(repository_id, doc_type, version_number)
    if not version:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_number} not found for document '{doc_type}'.",
        )
    return version


@router.post(
    "/{repository_id}/documents/{doc_type:path}/revert",
    response_model=ProjectDocumentResponse,
)
async def revert_document(
    repository_id: UUID,
    doc_type: str,
    body: RevertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revert document to a past version (creates a new version — non-destructive)."""
    await require_project_access(db, repository_id, current_user.id)
    repo = ProjectDocumentRepository(db)
    doc = await repo.revert_to_version(
        project_id=repository_id,
        doc_type=doc_type,
        version_number=body.version_number,
        user_id=current_user.id,
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Version {body.version_number} not found for document '{doc_type}'.",
        )
    await db.commit()
    await db.refresh(doc)
    return ProjectDocumentResponse.model_validate(doc)
