"""Tool executor — search_knowledge.

Allows agents to semantically search the project's RAG knowledge base.
Documents must be uploaded via the /api/v1/knowledge/{project_id}/documents
endpoint and reach status='indexed' before they appear in search results.
"""

from __future__ import annotations

import logging
import time

from backend.db.repositories.knowledge import KnowledgeRepository
from backend.services.embedding_service import EmbeddingError, EmbeddingService
from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError

logger = logging.getLogger(__name__)

# Lazily-created singleton — one instance per process is fine because
# EmbeddingService is stateless (Voyage AI client holds no mutable state).
_embedding_service: EmbeddingService | None = None


def _get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


async def run_search_knowledge(ctx: RunContext, tool_input: dict) -> str:
    """Search the project knowledge base using semantic similarity.

    Returns ranked text excerpts with source attribution (filename, chunk index,
    similarity score).  Returns a friendly message when no results are found
    rather than raising an error.
    """
    query: str = (tool_input.get("query") or "").strip()
    if not query:
        raise ToolExecutionError(
            message="'query' is required and must not be empty.",
            error_code="INVALID_INPUT",
            hint="Provide a natural-language description of what you're looking for.",
        )

    raw_limit = tool_input.get("limit", 5)
    try:
        limit = max(1, min(20, int(raw_limit)))
    except (TypeError, ValueError):
        limit = 5

    raw_threshold = tool_input.get("similarity_threshold", 0.4)
    try:
        threshold = max(0.0, min(1.0, float(raw_threshold)))
    except (TypeError, ValueError):
        threshold = 0.4

    t0 = time.monotonic()

    # 1. Embed the query
    try:
        svc = _get_embedding_service()
        query_vec = await svc.embed_query(query)
    except EmbeddingError as exc:
        raise ToolExecutionError(
            message=f"Could not embed search query: {exc}",
            error_code="SERVICE_ERROR",
            hint="Try again in a moment. If the issue persists, check VOYAGE_API_KEY.",
        ) from exc
    except RuntimeError as exc:
        # VOYAGE_API_KEY not set, or voyageai not installed
        raise ToolExecutionError(
            message=str(exc),
            error_code="SERVICE_ERROR",
            hint="Ask an admin to configure the Voyage AI API key for this deployment.",
        ) from exc

    # 2. Search
    repo = KnowledgeRepository(ctx.db)
    try:
        results = await repo.semantic_search(
            ctx.project.id,
            query_vec,
            query_text=query,
            limit=limit,
            similarity_threshold=threshold,
        )
    except Exception as exc:
        logger.exception("knowledge search failed for project=%s query=%r", ctx.project.id, query)
        raise ToolExecutionError(
            message=f"Knowledge search failed: {exc}",
            error_code="SERVICE_ERROR",
            hint="Try a simpler query or lower the similarity_threshold.",
        ) from exc

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if not results:
        return (
            f"No knowledge found for query: '{query}'\n"
            f"(threshold={threshold:.2f}, limit={limit}, elapsed={elapsed_ms}ms)\n\n"
            "Tip: Try a broader query or lower similarity_threshold (e.g. 0.3)."
        )

    # 3. Format results
    lines = [
        f"Found {len(results)} result(s) for: '{query}'  "
        f"(threshold={threshold:.2f}, elapsed={elapsed_ms}ms)\n"
    ]
    for i, r in enumerate(results, start=1):
        pct = f"{r.similarity_score * 100:.0f}%"
        source = r.filename
        if r.metadata and "page_num" in r.metadata:
            source += f" (page {r.metadata['page_num']})"

        # Truncate long excerpts
        excerpt = r.text_content
        if len(excerpt) > 500:
            excerpt = excerpt[:497] + "..."

        lines.append(f"[{i}] {source}  —  relevance {pct}")
        lines.append(excerpt)
        lines.append("")

    return "\n".join(lines)
