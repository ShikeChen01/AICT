"""Model context window catalog.

Maps known model names to their context window sizes (in tokens) and image
token costs. Used by PromptAssembly to compute model-specific budget allocations.

All supported models are vision-capable (image inputs accepted). The image
reserve is deducted from static_overhead so the dynamic pool (history, memory,
current session) grows/shrinks correctly as the user adjusts the image cap.

Image token estimates:
  Anthropic: (width × height) / 750, max ~1,590 at 1092×1092. Using 2,000 as
             conservative ceiling including overhead.
  OpenAI:    tile-based; ~1–2k per typical screenshot. Using 2,000.
  Gemini:    fixed ~1,120 tokens per image (Google documentation).
  Kimi:      OpenAI-compatible API; same tile cost estimate → 2,000.
"""

from __future__ import annotations

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # ── Anthropic ──────────────────────────────────────────────────
    "claude-opus-4-6":              200_000,
    "claude-opus-4.6":              200_000,
    "claude-sonnet-4-6":            200_000,
    "claude-sonnet-4.6":            200_000,

    # ── OpenAI ─────────────────────────────────────────────────────
    "gpt-5.2":                      400_000,
    "gpt-5":                        400_000,
    "gpt-4.1":                    1_000_000,
    "gpt-4.1-mini":               1_000_000,
    "gpt-4.1-nano":               1_000_000,

    # ── Google ─────────────────────────────────────────────────────
    "gemini-2.5-pro":             1_048_576,
    "gemini-2.5-flash":           1_048_576,
    "gemini-2.0-flash":           1_048_576,

    # ── Kimi / Moonshot ────────────────────────────────────────────
    "kimi-k2.5":                    262_144,  # 256k
}

DEFAULT_CONTEXT_WINDOW = 200_000  # safe fallback for unknown models

# ── Image input token cost per image ──────────────────────────────
# Tokens consumed per single image input (conservative ceiling).
# All listed models are vision-capable; absent = model not supported.
MODEL_IMAGE_TOKENS_PER_IMAGE: dict[str, int] = {
    # Anthropic — (w×h)/750 formula, max ~1,590; ceiling 2,000
    "claude-opus-4-6":   2_000,
    "claude-opus-4.6":   2_000,
    "claude-sonnet-4-6": 2_000,
    "claude-sonnet-4.6": 2_000,
    # OpenAI — tile-based, ceiling 2,000
    "gpt-5.2":           2_000,
    "gpt-5":             2_000,
    "gpt-4.1":           2_000,
    "gpt-4.1-mini":      2_000,
    "gpt-4.1-nano":      2_000,
    # Google — fixed ~1,120 per image (Gemini docs)
    "gemini-2.5-pro":    1_120,
    "gemini-2.5-flash":  1_120,
    "gemini-2.0-flash":  1_120,
    # Kimi — OpenAI-compatible; same tile estimate
    "kimi-k2.5":         2_000,
}

# Default max images per turn (applies to all models unless overridden).
# Claude agents can raise this via token_allocations.max_images_per_turn (1–20).
_DEFAULT_MAX_IMAGES = 10


def get_context_window(model: str) -> int:
    """Return context window size for the given model name.

    Exact match first, then longest-prefix match (to handle date-suffixed
    variants like 'gpt-5.2-2026-01-15'), then DEFAULT_CONTEXT_WINDOW.
    """
    if not model:
        return DEFAULT_CONTEXT_WINDOW

    m = model.lower()

    if m in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[m]

    best_prefix = ""
    for key in MODEL_CONTEXT_WINDOWS:
        if m.startswith(key) and len(key) > len(best_prefix):
            best_prefix = key
    if best_prefix:
        return MODEL_CONTEXT_WINDOWS[best_prefix]

    return DEFAULT_CONTEXT_WINDOW


def get_image_tokens_per_image(model: str) -> int:
    """Return the per-image token cost for the given model, or 0 if not vision-capable."""
    if not model:
        return 0

    m = model.lower()

    if m in MODEL_IMAGE_TOKENS_PER_IMAGE:
        return MODEL_IMAGE_TOKENS_PER_IMAGE[m]

    best_prefix = ""
    for key in MODEL_IMAGE_TOKENS_PER_IMAGE:
        if m.startswith(key) and len(key) > len(best_prefix):
            best_prefix = key
    if best_prefix:
        return MODEL_IMAGE_TOKENS_PER_IMAGE[best_prefix]

    return 0


def get_image_budget(model: str, max_images: int | None = None) -> int:
    """Return total image token reserve = tokens_per_image × max_images.

    If max_images is None, uses _DEFAULT_MAX_IMAGES.
    Returns 0 for models that are not vision-capable.
    """
    tpi = get_image_tokens_per_image(model)
    if tpi == 0:
        return 0
    cap = max_images if max_images is not None else _DEFAULT_MAX_IMAGES
    return tpi * cap


def model_supports_vision(model: str) -> bool:
    """Return True if the model is listed in MODEL_IMAGE_TOKENS_PER_IMAGE."""
    return get_image_tokens_per_image(model) > 0


def is_claude_model(model: str) -> bool:
    """Return True if the model is an Anthropic Claude model."""
    return model.lower().startswith(("claude-opus", "claude-sonnet", "claude-haiku", "claude-3"))


# Kept for one migration cycle — callers should switch to get_image_budget().
def get_image_reserve(model: str) -> int:
    """Deprecated: use get_image_budget() instead."""
    return get_image_budget(model)
