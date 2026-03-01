"""Model and provider resolution for the LLM layer.

Write-through design: the DB is the single source of truth.
- At agent creation: model and provider are copied from the template into the agent row.
- At user edit: model/provider are overwritten directly on the agent row.
- At runtime: the LLM layer reads agent.model and agent.provider directly. No fallback chain.

This module is kept for:
1. infer_provider() — safety fallback when agent.provider is NULL (pre-migration agents)
2. default_model_for_role() — used by agent_service.py when creating agents without a template
"""

from __future__ import annotations

import re

from backend.config import settings

_OPENAI_O_SERIES_RE = re.compile(r"^o\d")


def infer_provider(model: str) -> str:
    """Infer provider from model name.

    Used as a fallback when agent.provider is not explicitly set.
    Prefer reading agent.provider directly from DB wherever possible.
    """
    m = (model or "").lower()
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "gemini" in m or "google" in m:
        return "google"
    if (
        "kimi" in m
        or "moonshot" in m
        or m.startswith("k2")
        or m.startswith("kimi-k2")
        or m.startswith("moonshot-v1")
    ):
        return "kimi"
    if "gpt" in m or "chatgpt" in m or "openai" in m or _OPENAI_O_SERIES_RE.match(m):
        return "openai"
    # No match — fall back to anthropic if configured
    return "anthropic"


def default_model_for_role(role: str | None) -> str:
    """Return the global default model for a given role.

    Used only at agent creation when no template is available.
    For all other cases, read agent.model from DB directly.
    """
    role_norm = (role or "").strip().lower()
    if role_norm == "manager":
        return settings.manager_model_default
    if role_norm == "cto":
        return settings.cto_model_default
    return settings.engineer_junior_model


def resolve_provider(agent_provider: str | None, model: str) -> str:
    """Return the provider to use for an LLM call.

    Primary path: use agent.provider from DB (always set after migration 015).
    Fallback: infer from model name (for pre-migration agents where provider is NULL).
    """
    if agent_provider:
        return agent_provider.lower()
    return infer_provider(model)


# ── Backward-compatibility shim ──────────────────────────────────────────────
# The old resolve_model() function is kept so existing code (e.g., tests) that
# imports it doesn't break immediately. It now just returns agent.model directly
# since the DB is the source of truth.

def resolve_model(
    role: str,
    *,
    seniority: str | None = None,
    model_override: str | None = None,
    project_model_overrides: dict | None = None,
) -> str:
    """Deprecated: DB is the source of truth. Return model_override if provided, else default."""
    if model_override:
        return model_override
    if project_model_overrides:
        role_key = f"{role}_{seniority}" if seniority else role
        if role_key in project_model_overrides:
            return project_model_overrides[role_key]
        if role in project_model_overrides:
            return project_model_overrides[role]
    return default_model_for_role(role)


def normalize_seniority(seniority: str | None) -> str:
    """Deprecated: normalize seniority string."""
    if not seniority:
        return "junior"
    s = seniority.strip().lower()
    return s if s in ("junior", "intermediate", "senior") else "junior"
