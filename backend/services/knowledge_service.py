"""
Knowledge ingestion service — parse → chunk → embed → store.

Supports: PDF (pymupdf), plain text, Markdown, CSV.

Usage:
    svc = KnowledgeService()
    doc = await svc.ingest(
        db=db,
        project_id=project_id,
        filename="spec.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        data=raw_bytes,
        user_id=current_user.id,
    )
"""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import KnowledgeChunk, KnowledgeDocument, KNOWLEDGE_VALID_FILE_TYPES
from backend.services.embedding_service import EmbeddingService, EmbeddingError

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_CHARS_PER_TOKEN_ESTIMATE = 4  # conservative estimate, avoids tokenizer dependency
_MAX_CHUNK_CHARS = settings.knowledge_chunk_size_tokens * _CHARS_PER_TOKEN_ESTIMATE
_OVERLAP_CHARS = settings.knowledge_chunk_overlap_tokens * _CHARS_PER_TOKEN_ESTIMATE


# ── Chunk dataclass ──────────────────────────────────────────────────────────

@dataclass
class ChunkInfo:
    text: str
    char_count: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Main service class ───────────────────────────────────────────────────────

class KnowledgeService:
    """Orchestrates parsing, chunking, embedding, and DB storage."""

    def __init__(self, embedding_service: EmbeddingService | None = None):
        self._embed = embedding_service or EmbeddingService()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def ingest(
        self,
        db: AsyncSession,
        project_id: UUID,
        filename: str,
        file_type: str,
        mime_type: str,
        data: bytes,
        user_id: UUID | None = None,
    ) -> KnowledgeDocument:
        """Full pipeline: create record → parse → chunk → embed → persist."""

        file_type = file_type.lower()
        if file_type not in KNOWLEDGE_VALID_FILE_TYPES:
            raise ValueError(
                f"Unsupported file type '{file_type}'. "
                f"Allowed: {', '.join(sorted(KNOWLEDGE_VALID_FILE_TYPES))}"
            )

        # 1. Create document record (status = indexing)
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            project_id=project_id,
            uploaded_by_user_id=user_id,
            filename=filename,
            file_type=file_type,
            mime_type=mime_type,
            original_size_bytes=len(data),
            status="indexing",
        )
        db.add(doc)
        await db.flush()

        try:
            # 2. Parse text
            text = self._parse(file_type, data, filename)

            # 3. Chunk
            chunks = self._chunk(text, file_type)
            if not chunks:
                raise ValueError("Document produced no text chunks after parsing.")

            # 4. Embed
            chunk_texts = [c.text for c in chunks]
            vectors = await self._embed.embed_documents(chunk_texts)

            # 5. Insert chunks
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                db_chunk = KnowledgeChunk(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    project_id=project_id,
                    chunk_index=i,
                    text_content=chunk.text,
                    char_count=chunk.char_count,
                    token_count=chunk.token_count,
                    embedding=vector,
                    metadata_=chunk.metadata or None,
                )
                db.add(db_chunk)

            # 6. Mark indexed
            doc.chunk_count = len(chunks)
            doc.status = "indexed"
            doc.indexed_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(
                "knowledge_service.ingest: doc=%s project=%s file=%s chunks=%d bytes=%d",
                doc.id, project_id, filename, len(chunks), len(data),
            )

        except Exception as exc:
            doc.status = "failed"
            doc.error_message = str(exc)[:1000]
            await db.flush()
            logger.error(
                "knowledge_service.ingest failed: doc=%s file=%s error=%s",
                doc.id, filename, exc,
            )
            raise

        return doc

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self, file_type: str, data: bytes, filename: str) -> str:
        """Extract raw text from the binary payload."""
        if file_type == "pdf":
            return self._parse_pdf(data)
        elif file_type in ("txt", "markdown"):
            return self._parse_text(data)
        elif file_type == "csv":
            return self._parse_csv(data)
        else:
            raise ValueError(f"No parser for file_type '{file_type}'")

    @staticmethod
    def _parse_pdf(data: bytes) -> str:
        try:
            import fitz  # pymupdf  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pymupdf is not installed. Add 'pymupdf>=1.25.0' to requirements.txt."
            ) from exc

        parts: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                if text:
                    parts.append(f"[Page {page_num}]\n{text}")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_text(data: bytes) -> str:
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_csv(data: bytes) -> str:
        """Convert CSV rows to human-readable 'Row N: col=val, ...' format."""
        text = KnowledgeService._parse_text(data)
        lines: list[str] = []
        try:
            reader = csv.DictReader(io.StringIO(text))
            for i, row in enumerate(reader, start=1):
                row_parts = [f"{k}={v}" for k, v in row.items() if v is not None]
                lines.append(f"Row {i}: {', '.join(row_parts)}")
        except Exception:
            # Fallback: return raw text
            return text
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk(self, text: str, file_type: str) -> list[ChunkInfo]:
        """Split text into overlapping chunks, respecting paragraph boundaries."""
        paragraphs = self._split_paragraphs(text)
        chunks: list[ChunkInfo] = []
        current: list[str] = []
        current_len = 0
        overlap_tail = ""

        for para in paragraphs:
            para_len = len(para)

            # If a single paragraph is longer than max, split at sentence level
            if para_len > _MAX_CHUNK_CHARS:
                # Flush current buffer first
                if current:
                    chunks.append(self._make_chunk(overlap_tail + "\n\n".join(current)))
                    overlap_tail = self._tail("\n\n".join(current))
                    current, current_len = [], 0

                # Sentence-split the long paragraph
                for sub in self._split_sentences(para):
                    if current_len + len(sub) > _MAX_CHUNK_CHARS and current:
                        chunks.append(self._make_chunk(overlap_tail + "\n".join(current)))
                        overlap_tail = self._tail("\n".join(current))
                        current, current_len = [], 0
                    current.append(sub)
                    current_len += len(sub)
                continue

            if current_len + para_len > _MAX_CHUNK_CHARS and current:
                chunks.append(self._make_chunk(overlap_tail + "\n\n".join(current)))
                overlap_tail = self._tail("\n\n".join(current))
                current, current_len = [], 0

            current.append(para)
            current_len += para_len

        # Flush remainder
        if current:
            chunks.append(self._make_chunk(overlap_tail + "\n\n".join(current)))

        return chunks

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """Split on blank lines; filter empty strings."""
        import re
        return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Very lightweight sentence splitter — avoids NLTK dependency."""
        import re
        # Split after . ! ? followed by whitespace or end-of-string
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _tail(text: str) -> str:
        """Return the last _OVERLAP_CHARS characters (prepended to next chunk)."""
        if not text or _OVERLAP_CHARS == 0:
            return ""
        tail = text[-_OVERLAP_CHARS:].strip()
        return tail + "\n\n" if tail else ""

    @staticmethod
    def _make_chunk(text: str) -> ChunkInfo:
        text = text.strip()
        chars = len(text)
        tokens = max(1, chars // _CHARS_PER_TOKEN_ESTIMATE)
        metadata: dict[str, Any] = {}
        match = re.search(r"\[Page (\d+)\]", text)
        if match:
            metadata["page_num"] = int(match.group(1))
        return ChunkInfo(text=text, char_count=chars, token_count=tokens, metadata=metadata)
