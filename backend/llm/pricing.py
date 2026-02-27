"""LLM cost estimation using the pricing table defined in backend/config.py.

Usage:
    from backend.llm.pricing import estimate_cost_usd

    cost = estimate_cost_usd("claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
    # → 0.01050  (USD)

Pricing lookup priority:
  1. Exact model name match in LLM_MODEL_PRICING.
  2. Longest prefix match (e.g. "claude-sonnet-4-6-20251030" matches "claude-sonnet-4-6").
  3. No match → returns 0.0 (cost unknown; recorded as free).
"""

from __future__ import annotations

from backend.config import LLM_MODEL_PRICING


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return estimated cost in USD for a single LLM call.

    Prices come from ``LLM_MODEL_PRICING`` in ``backend/config.py``.
    Returns 0.0 if the model is not in the pricing table.
    """
    pricing = _find_pricing(model)
    if not pricing:
        return 0.0
    return (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000


def _find_pricing(model: str) -> dict[str, float] | None:
    """Find pricing by exact match first, then longest prefix match."""
    if model in LLM_MODEL_PRICING:
        return LLM_MODEL_PRICING[model]

    best_prefix = ""
    best_pricing: dict[str, float] | None = None
    for prefix, pricing in LLM_MODEL_PRICING.items():
        if model.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_pricing = pricing
    return best_pricing


def cost_for_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    """Return a dict with cost breakdown (useful for API responses)."""
    usd = estimate_cost_usd(model, input_tokens, output_tokens)
    pricing = _find_pricing(model)
    return {
        "estimated_cost_usd": round(usd, 6),
        "has_pricing": pricing is not None,
    }
