"""Per-user API key management — CRUD + test endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import get_current_user
from backend.db.models import User
from backend.db.repositories.user_api_keys import UserAPIKeyRepository, VALID_PROVIDERS
from backend.db.session import get_db
from backend.schemas.api_keys import APIKeyResponse, APIKeyUpsertRequest, APIKeyTestResponse
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/api-keys", tags=["api-keys"])


def _get_repo(db: AsyncSession) -> UserAPIKeyRepository:
    return UserAPIKeyRepository(db, encryption_key=settings.secret_encryption_key)


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List configured API keys for the current user (masked)."""
    repo = _get_repo(db)
    keys = await repo.list_for_user(current_user.id)
    return [
        APIKeyResponse(provider=k.provider, display_hint=k.display_hint, is_valid=k.is_valid)
        for k in keys
    ]


@router.put("/{provider}", response_model=APIKeyResponse)
async def upsert_api_key(
    provider: str,
    body: APIKeyUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update an API key for a provider."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {provider}. Valid: {', '.join(sorted(VALID_PROVIDERS))}",
        )

    repo = _get_repo(db)
    key = await repo.upsert(current_user.id, provider, body.api_key)
    await db.commit()
    await db.refresh(key)
    return APIKeyResponse(provider=key.provider, display_hint=key.display_hint, is_valid=key.is_valid)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an API key for a provider (reverts to server fallback)."""
    repo = _get_repo(db)
    deleted = await repo.delete_key(current_user.id, provider)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.commit()


@router.post("/{provider}/test", response_model=APIKeyTestResponse)
async def test_api_key(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an API key by validating it can create a provider instance."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    repo = _get_repo(db)
    plaintext = await repo.get_decrypted_key(current_user.id, provider)
    if not plaintext:
        return APIKeyTestResponse(valid=False, error="No API key configured for this provider")

    try:
        from backend.llm.router import ProviderRouter
        test_models = {
            "anthropic": "claude-haiku-4-5",
            "openai": "gpt-4o-mini",
            "google": "gemini-2.0-flash-lite",
            "moonshot": "kimi-k2",
        }
        test_model = test_models.get(provider, "")
        router_instance = ProviderRouter()
        router_instance.get_provider(test_model, provider=provider, api_key=plaintext)
        return APIKeyTestResponse(valid=True)
    except Exception as exc:
        logger.warning("API key test failed for %s: %s", provider, exc)
        await repo.mark_invalid(current_user.id, provider)
        await db.commit()
        return APIKeyTestResponse(valid=False, error=str(exc))
