"""
Knowledge base repository — CRUD for KnowledgeDocument + vector similarity
search for KnowledgeChunk.

Usage:
    repo = KnowledgeRepository(db)
    docs = await repo.list_by_project(project_id)
    results = await repo.semantic_search(project_id, query_embedding, limit=10)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import KnowledgeChunk, KnowledgeDocument, ProjectSettings
from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    filename: str
    file_type: str
    chunk_index: int
    text_content: str
    similarity_score: float
    metadata: dict[str, Any] | None


# ── Repository ───────────────────────────────────────────────────────────────

class KnowledgeRepository(BaseRepository[KnowledgeDocument]):

    def __init__(self, session: AsyncSession):
        super().__init__(KnowledgeDocument, session)

    # ------------------------------------------------------------------
    # Document CRUD
    # ------------------------------------------------------------------

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.project_id == project_id)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(KnowledgeDocument.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_project(
        self, project_id: UUID, document_id: UUID
    ) -> KnowledgeDocument | None:
        result = await self.session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_document(self, project_id: UUID, document_id: UUID) -> bool:
        doc = await self.get_by_project(project_id, document_id)
        if doc is None:
            return False
        await self.session.delete(doc)
        await self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Quota / Stats
    # ------------------------------------------------------------------

    async def get_project_stats(self, project_id: UUID) -> dict[str, int]:
        """Return aggregate document count, chunk count, and total bytes."""
        doc_q = await self.session.execute(
            select(
                func.count(KnowledgeDocument.id).label("total_docs"),
                func.count(KnowledgeDocument.id)
                .filter(KnowledgeDocument.status == "indexed")
                .label("indexed_docs"),
                func.coalesce(func.sum(KnowledgeDocument.original_size_bytes), 0).label(
                    "total_bytes"
                ),
            ).where(KnowledgeDocument.project_id == project_id)
        )
        row = doc_q.one()

        chunk_q = await self.session.execute(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.project_id == project_id
            )
        )
        total_chunks = chunk_q.scalar_one()

        return {
            "total_documents": row.total_docs,
            "indexed_documents": row.indexed_docs,
            "total_chunks": total_chunks,
            "total_bytes": row.total_bytes,
        }

    async def get_project_quotas(self, project_id: UUID) -> dict[str, int]:
        """Read per-project knowledge quotas from ProjectSettings."""
        result = await self.session.execute(
            select(
                ProjectSettings.knowledge_max_documents,
                ProjectSettings.knowledge_max_total_bytes,
            ).where(ProjectSettings.project_id == project_id)
        )
        row = result.one_or_none()
        if row is None:
            return {"max_documents": 50, "max_total_bytes": 100 * 1024 * 1024}
        return {
            "max_documents": row.knowledge_max_documents,
            "max_total_bytes": row.knowledge_max_total_bytes,
        }

    async def check_quota(self, project_id: UUID) -> tuple[bool, str]:
        """Return (ok, message).  ok=False means quota is exceeded."""
        stats = await self.get_project_stats(project_id)
        quotas = await self.get_project_quotas(project_id)

        max_docs = quotas["max_documents"]
        if max_docs > 0 and stats["total_documents"] >= max_docs:
            return False, (
                f"Project has reached its document quota ({max_docs} documents). "
                "Delete existing documents to upload more."
            )

        max_bytes = quotas["max_total_bytes"]
        if max_bytes > 0 and stats["total_bytes"] >= max_bytes:
            mb = max_bytes // (1024 * 1024)
            return False, (
                f"Project has reached its storage quota ({mb} MB). "
                "Delete existing documents to upload more."
            )

        return True, ""

    # ------------------------------------------------------------------
    # Vector similarity search
    # ------------------------------------------------------------------

    async def semantic_search(
        self,
        project_id: UUID,
        query_embedding: list[float],
        *,
        limit: int = 10,
        similarity_threshold: float = 0.4,
    ) -> list[SearchResult]:
        """Cosine similarity search using pgvector.

        Returns results ordered by similarity descending, filtered by
        project_id and the similarity threshold.

        Falls back gracefully if pgvector is not available (returns empty list).
        """
        try:
            return await self._pgvector_search(
                project_id, query_embedding, limit=limit,
                similarity_threshold=similarity_threshold,
            )
        except Exception as exc:
            # If pgvector is not available (e.g. test env without extension),
            # log and return empty rather than 500-ing
            if "vector" in str(exc).lower() or "pgvector" in str(exc).lower():
                logger.warning("pgvector search unavailable: %s", exc)
                return []
            raise

    async def _pgvector_search(
        self,
        project_id: UUID,
        query_embedding: list[float],
        *,
        limit: int,
        similarity_threshold: float,
    ) -> list[SearchResult]:
        """Raw SQL cosine-similarity query via pgvector <=> operator."""
        # Build the query vector literal for pgvector
        vec_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = text("""
            SELECT
                kc.id               AS chunk_id,
                kc.document_id      AS document_id,
                kd.filename         AS filename,
                kd.file_type        AS file_type,
                kc.chunk_index      AS chunk_index,
                kc.text_content     AS text_content,
                kc.metadata_        AS metadata,
                (1 - (kc.embedding <=> CAST(:query_vec AS vector)))
                                    AS similarity_score
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd
                ON kc.document_id = kd.id
            WHERE kc.project_id = :project_id
              AND kd.status = 'indexed'
              AND kc.embedding IS NOT NULL
              AND (1 - (kc.embedding <=> CAST(:query_vec AS vector))) >= :threshold
            ORDER BY similarity_score DESC
            LIMIT :limit
        """)

        result = await self.session.execute(
            sql,
            {
                "query_vec": vec_literal,
                "project_id": str(project_id),
                "threshold": similarity_threshold,
                "limit": limit,
            },
        )
        rows = result.mappings().all()

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                filename=row["filename"],
                file_type=row["file_type"],
                chunk_index=row["chunk_index"],
                text_content=row["text_content"],
                similarity_score=float(row["similarity_score"]),
                metadata=row["metadata"],
            )
            for row in rows
        ]
