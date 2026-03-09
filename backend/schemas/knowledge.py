"""
Pydantic schemas for the RAG knowledge base API (Feature 1.6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Document ────────────────────────────────────────────────────────────


class KnowledgeDocumentResponse(BaseModel):
    """Metadata returned after upload or when listing documents."""

    id: UUID
    project_id: UUID
    filename: str
    file_type: str
    mime_type: str
    original_size_bytes: int
    chunk_count: int
    status: str  # pending | indexing | indexed | failed
    error_message: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Search ──────────────────────────────────────────────────────────────


class KnowledgeSearchRequest(BaseModel):
    """Body for POST /{project_id}/search."""

    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language search query")
    limit: int = Field(default=10, ge=1, le=50, description="Max results to return")
    similarity_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity (0 = any, 1 = exact). Lower = more results.",
    )


class KnowledgeSearchResult(BaseModel):
    """A single ranked result from a knowledge search."""

    chunk_id: UUID
    document_id: UUID
    filename: str
    file_type: str
    chunk_index: int
    text_content: str
    similarity_score: float
    metadata: dict[str, Any] | None = None


class KnowledgeSearchResponse(BaseModel):
    """Response for POST /{project_id}/search."""

    query: str
    result_count: int
    results: list[KnowledgeSearchResult]
    duration_ms: int


# ── Stats ───────────────────────────────────────────────────────────────


class KnowledgeStatsResponse(BaseModel):
    """Aggregate stats for a project's knowledge base."""

    project_id: UUID
    total_documents: int
    indexed_documents: int
    total_chunks: int
    total_bytes: int
    quota_documents: int   # from ProjectSettings
    quota_bytes: int       # from ProjectSettings
