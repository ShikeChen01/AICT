from __future__ import annotations

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
) -> str:
    role_norm = (role or "").strip().lower()
    if role_norm == "engineer":
        return _engineer_model_for_seniority(seniority)

    explicit = normalize_model_name(model_override)
    if explicit:
        return explicit
    return default_model_for_role(role)
