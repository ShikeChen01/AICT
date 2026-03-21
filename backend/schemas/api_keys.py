"""Request/response schemas for per-user API key management."""

from pydantic import BaseModel


class APIKeyResponse(BaseModel):
    provider: str
    display_hint: str | None
    is_valid: bool


class APIKeyUpsertRequest(BaseModel):
    api_key: str


class APIKeyTestResponse(BaseModel):
    valid: bool
    error: str | None = None
