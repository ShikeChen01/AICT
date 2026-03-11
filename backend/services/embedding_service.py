"""
Embedding service — thin async wrapper around Voyage AI.

Usage:
    from backend.services.embedding_service import EmbeddingService

    svc = EmbeddingService()
    vectors = await svc.embed_documents(["chunk one", "chunk two"])
    query_vec = await svc.embed_query("authentication flow")
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from backend.config import settings

logger = logging.getLogger(__name__)

# Voyage AI SDK is async-unfriendly (synchronous HTTP under the hood), so we
# run each call inside asyncio.to_thread() to avoid blocking the event loop.
# The SDK itself is imported lazily so the app still starts if voyageai isn't
# installed (e.g. during certain test runs that mock the service entirely).

_VOYAGE_MODEL = None  # resolved on first use


def _get_voyage_client():
    """Return (and cache) a synchronous Voyage AI client."""
    global _VOYAGE_MODEL
    if _VOYAGE_MODEL is not None:
        return _VOYAGE_MODEL

    try:
        import voyageai  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "voyageai package is not installed. "
            "Add 'voyageai>=0.3.0,<1.0.0' to requirements.txt."
        ) from exc

    api_key = settings.voyage_api_key
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set. Add it to your .env file."
        )

    _VOYAGE_MODEL = voyageai.Client(api_key=api_key)
    return _VOYAGE_MODEL


class EmbeddingError(Exception):
    """Raised when Voyage AI returns an unexpected error."""


def _is_retryable(exc: Exception) -> bool:
    """Determine whether an embedding API error is transient and worth retrying.

    Retryable conditions: HTTP 429 (rate-limit), 5xx server errors, and
    connection/timeout exceptions.  The previous heuristic ("5" in str[:3])
    matched false positives like "500 Internal" but also "5 results found".
    """
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    error_str = str(exc).lower()
    # Explicit status codes we know are transient
    for code in ("429", "500", "502", "503", "504"):
        if code in error_str:
            return True
    return False


class EmbeddingService:
    """Async wrapper for Voyage AI text embeddings.

    Documents are embedded with input_type="document" (optimised for storage).
    Queries are embedded with input_type="query" (optimised for retrieval).
    Batching is handled automatically; max batch size is configurable via
    settings.knowledge_embed_batch_size.
    """

    def __init__(self, model: str | None = None):
        self._model = model or settings.voyage_model
        self._batch_size = settings.knowledge_embed_batch_size

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document chunks.  Returns one vector per text."""
        return await self._embed_batched(texts, input_type="document")

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query string."""
        results = await self._embed_batched([text], input_type="query")
        return results[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _embed_batched(
        self,
        texts: list[str],
        input_type: str,
    ) -> list[list[float]]:
        """Split *texts* into batches and embed each batch, with retry."""
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            vectors = await self._embed_single_batch(batch, input_type)
            all_vectors.extend(vectors)

        return all_vectors

    async def _embed_single_batch(
        self,
        texts: list[str],
        input_type: str,
        *,
        max_retries: int = 3,
    ) -> list[list[float]]:
        """Call Voyage AI for one batch; retries on transient errors."""
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                result = await asyncio.to_thread(
                    self._call_voyage_sync, texts, input_type
                )
                return result
            except Exception as exc:
                last_exc = exc
                retryable = _is_retryable(exc)
                if not retryable or attempt == max_retries:
                    break
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(
                    "Voyage AI embedding attempt %d/%d failed (%s), retrying in %ds",
                    attempt, max_retries, exc, wait,
                )
                await asyncio.sleep(wait)

        raise EmbeddingError(
            f"Voyage AI embedding failed after {max_retries} attempts: {last_exc}"
        ) from last_exc

    def _call_voyage_sync(
        self,
        texts: list[str],
        input_type: str,
    ) -> list[list[float]]:
        """Synchronous Voyage AI call — run via asyncio.to_thread."""
        client = _get_voyage_client()
        response = client.embed(
            texts,
            model=self._model,
            input_type=input_type,
        )
        return response.embeddings
