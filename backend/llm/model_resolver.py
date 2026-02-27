from __future__ import annotations

from typing import Any

from backend.config import settings

ENGINEER_SENIORITY_LEVELS = ("junior", "intermediate", "senior")


def normalize_seniority(seniority: str | None) -> str:
    value = (seniority or "").strip().lower()
    if value not in ENGINEER_SENIORITY_LEVELS:
        return "junior"
    return value


def normalize_tier(tier: str | None) -> str:
    """Backward-compatible alias for persisted `tier` field values."""
    return normalize_seniority(tier)


def normalize_model_name(model: str | None) -> str | None:
    value = (model or "").strip()
    return value or None


def default_model_for_role(role: str | None) -> str:
    role_norm = (role or "").strip().lower()
    if role_norm == "manager":
        return settings.manager_model_default
    if role_norm == "cto":
        return settings.cto_model_default
    if role_norm == "engineer":
        return settings.engineer_junior_model
    return settings.manager_model_default


def _engineer_model_for_seniority(seniority: str | None) -> str:
    normalized = normalize_seniority(seniority)
    if normalized == "senior":
        return settings.engineer_senior_model
    if normalized == "intermediate":
        return settings.engineer_intermediate_model
    return settings.engineer_junior_model


def resolve_model(
    role: str | None,
    *,
    seniority: str | None = None,
    model_override: str | None = None,
    project_model_overrides: dict[str, Any] | None = None,
) -> str:
    """Resolve the model string for an agent.

    Priority (highest to lowest):
    1. Project-level ``model_overrides`` from ``project_settings``
       (keys: manager, cto, engineer_junior, engineer_intermediate, engineer_senior).
       Project settings are the authoritative live source — they must win over any
       model baked into the agents row at spawn time so that changing Settings takes
       effect immediately without re-spawning agents.
    2. Per-agent ``model_override`` stored on the ``agents`` row (explicit per-agent
       override set via API/tool — only falls through here when no project override
       exists for the role).
    3. Global defaults from ``backend.config.settings``.
    """
    role_norm = (role or "").strip().lower()

    # 1. Project-level overrides — live, authoritative
    if project_model_overrides:
        if role_norm == "engineer":
            tier_key = f"engineer_{normalize_seniority(seniority)}"
            project_model = normalize_model_name(project_model_overrides.get(tier_key))
            if project_model:
                return project_model
        else:
            project_model = normalize_model_name(project_model_overrides.get(role_norm))
            if project_model:
                return project_model

    # 2. Per-agent override (explicit, e.g. set via API or future per-agent UI)
    explicit = normalize_model_name(model_override)
    if explicit:
        return explicit

    # 3. Global defaults
    if role_norm == "engineer":
        return _engineer_model_for_seniority(seniority)

    return default_model_for_role(role)
