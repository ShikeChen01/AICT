"""
Knowledge Base REST API (Feature 1.6 — RAG).

Endpoints:
  POST   /{project_id}/documents          — upload & ingest a document
  GET    /{project_id}/documents          — list documents
  GET    /{project_id}/documents/{doc_id} — get single document
  DELETE /{project_id}/documents/{doc_id} — delete document + chunks
  POST   /{project_id}/search             — semantic search (for UI testing)
  GET    /{project_id}/stats              — usage/quota stats
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import KNOWLEDGE_VALID_FILE_TYPES, User
from backend.db.repositories.knowledge import KnowledgeRepository
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.schemas.knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    KnowledgeStatsResponse,
)
from backend.services.embedding_service import EmbeddingError, EmbeddingService
from backend.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# File-type → expected MIME prefixes (for basic validation)
_MIME_TO_FILE_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "text/csv": "csv",
    "application/csv": "csv",
    "application/octet-stream": "",  # fall back to extension
}

_EXT_TO_FILE_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".csv": "csv",
}


def _detect_file_type(filename: str, mime_type: str) -> str:
    """Detect file_type from MIME or extension; raise 415 if unsupported."""
    ft = _MIME_TO_FILE_TYPE.get(mime_type.lower().split(";")[0].strip(), "")
    if not ft:
        # Fall back to extension
        import os
        ext = os.path.splitext(filename)[1].lower()
        ft = _EXT_TO_FILE_TYPE.get(ext, "")
    if not ft or ft not in KNOWLEDGE_VALID_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type (mime='{mime_type}', file='{filename}'). "
                f"Allowed: PDF, TXT, Markdown (.md), CSV"
            ),
        )
    return ft


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a knowledge document",
)
async def upload_knowledge_document(
    project_id: UUID,
    file: UploadFile = File(..., description="PDF, TXT, Markdown, or CSV file"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentResponse:
    """Upload a document to the project knowledge base.

    The document is parsed, chunked, and embedded asynchronously during
    this request.  On success the document status will be 'indexed'.
    On parsing / embedding failure the status will be 'failed' with an
    error_message.
    """
    await require_project_access(db, project_id, current_user.id)

    # Quota check
    repo = KnowledgeRepository(db)
    ok, msg = await repo.check_quota(project_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg)

    # Size guard
    max_bytes = settings.knowledge_max_file_size_bytes
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.",
        )
    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    filename = (file.filename or "upload").strip() or "upload"
    mime_type = (file.content_type or "application/octet-stream").strip()
    file_type = _detect_file_type(filename, mime_type)

    svc = KnowledgeService()
    try:
        doc = await svc.ingest(
            db=db,
            project_id=project_id,
            filename=filename,
            file_type=file_type,
            mime_type=mime_type,
            data=data,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    await db.commit()
    await db.refresh(doc)

    logger.info(
        "knowledge.upload: doc=%s project=%s file=%s size=%d status=%s",
        doc.id, project_id, filename, len(data), doc.status,
    )
    return KnowledgeDocumentResponse.model_validate(doc)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/documents",
    response_model=list[KnowledgeDocumentResponse],
    summary="List knowledge documents for a project",
)
async def list_knowledge_documents(
    project_id: UUID,
    status_filter: str | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeDocumentResponse]:
    """Return all documents in the project's knowledge base."""
    await require_project_access(db, project_id, current_user.id)
    repo = KnowledgeRepository(db)
    docs = await repo.list_by_project(project_id, status=status_filter, limit=min(limit, 200))
    return [KnowledgeDocumentResponse.model_validate(d) for d in docs]


# ── Get single ───────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
    summary="Get a single knowledge document",
)
async def get_knowledge_document(
    project_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentResponse:
    await require_project_access(db, project_id, current_user.id)
    repo = KnowledgeRepository(db)
    doc = await repo.get_by_project(project_id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return KnowledgeDocumentResponse.model_validate(doc)


# ── Delete ───────────────────────────────────────────────────────────────────

@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge document and its chunks",
)
async def delete_knowledge_document(
    project_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await require_project_access(db, project_id, current_user.id)
    repo = KnowledgeRepository(db)
    deleted = await repo.delete_document(project_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    await db.commit()
    logger.info(
        "knowledge.delete: doc=%s project=%s user=%s",
        document_id, project_id, current_user.id,
    )


# ── Search (UI helper) ───────────────────────────────────────────────────────

@router.post(
    "/{project_id}/search",
    response_model=KnowledgeSearchResponse,
    summary="Semantic search over the project knowledge base",
)
async def search_knowledge(
    project_id: UUID,
    body: KnowledgeSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSearchResponse:
    """Semantic similarity search — intended for frontend UI testing.

    Agents should use the search_knowledge *tool* instead.
    """
    await require_project_access(db, project_id, current_user.id)

    t0 = time.monotonic()

    embed_svc = EmbeddingService()
    try:
        query_vec = await embed_svc.embed_query(body.query)
    except (EmbeddingError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Embedding service unavailable: {exc}",
        )

    repo = KnowledgeRepository(db)
    raw = await repo.semantic_search(
        project_id,
        query_vec,
        query_text=body.query,
        limit=body.limit,
        similarity_threshold=body.similarity_threshold,
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    results = [
        KnowledgeSearchResult(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            file_type=r.file_type,
            chunk_index=r.chunk_index,
            text_content=r.text_content,
            similarity_score=r.similarity_score,
            metadata=r.metadata,
        )
        for r in raw
    ]

    return KnowledgeSearchResponse(
        query=body.query,
        result_count=len(results),
        results=results,
        duration_ms=elapsed_ms,
    )


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/stats",
    response_model=KnowledgeStatsResponse,
    summary="Get knowledge base usage and quota stats",
)
async def get_knowledge_stats(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeStatsResponse:
    await require_project_access(db, project_id, current_user.id)
    repo = KnowledgeRepository(db)
    stats = await repo.get_project_stats(project_id)
    quotas = await repo.get_project_quotas(project_id)
    return KnowledgeStatsResponse(
        project_id=project_id,
        total_documents=stats["total_documents"],
        indexed_documents=stats["indexed_documents"],
        total_chunks=stats["total_chunks"],
        total_bytes=stats["total_bytes"],
        quota_documents=quotas["max_documents"],
        quota_bytes=quotas["max_total_bytes"],
    )
