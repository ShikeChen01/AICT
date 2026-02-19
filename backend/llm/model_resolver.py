from __future__ import annotations

from backend.config import settings


def normalize_tier(tier: str | None) -> str | None:
    value = (tier or "").strip().lower()
    return value or None


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
        return settings.engineer_model_default
    return settings.claude_model


def _tier_model_for_role(role: str | None, tier: str | None) -> str | None:
    role_norm = (role or "").strip().lower()
    tier_norm = normalize_tier(tier)
    if not role_norm or not tier_norm:
        return None
    configured = settings.agent_tier_models.get(f"{role_norm}:{tier_norm}")
    return normalize_model_name(configured)


def resolve_model(role: str | None, *, tier: str | None = None, model_override: str | None = None) -> str:
    explicit = normalize_model_name(model_override)
    if explicit:
        return explicit
    tier_model = _tier_model_for_role(role, tier)
    if tier_model:
        return tier_model
    return default_model_for_role(role)
