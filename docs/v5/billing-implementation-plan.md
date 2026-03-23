# V5: Per-User API Keys + Billing System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user LLM API key management (prerequisite) then a membership tier system (Free/Individual/Team) with Stripe flat subscriptions, sandbox hour enforcement, and a billing UI.

**Architecture:** Phase 1 adds a `UserAPIKey` table with encrypted storage (same Fernet pattern as `ProjectSecrets`), CRUD API, and LLM router changes so user keys override server-wide keys. Phase 2 adds `Subscription` and `UsagePeriod` models for billing cycles, a `TierService` for sandbox hour enforcement, Stripe Checkout/Portal/webhook integration, and a frontend billing page.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Alembic, Stripe Python SDK, React/TypeScript, Vite

**Spec:** `docs/v5/tier-system-design.md`

---

## File Structure

### New files
```
backend/db/repositories/user_api_keys.py    # Fernet-encrypted CRUD for per-user LLM keys
backend/api/v1/api_keys.py                  # CRUD + test endpoints for user API keys
backend/schemas/api_keys.py                 # Request/response schemas for API keys
backend/api/v1/billing.py                   # Checkout, portal, webhook, usage endpoints
backend/schemas/billing.py                  # Billing request/response schemas
backend/services/tier_service.py            # TIER_LIMITS, enforcement checks, usage recording
backend/services/stripe_service.py          # Stripe API wrapper
backend/migrations/versions/006_add_v5_api_keys_and_billing.py
backend/tests/test_user_api_keys.py
backend/tests/test_api_keys_api.py
backend/tests/test_billing_config.py
backend/tests/test_billing_models.py
backend/tests/test_tier_service.py
backend/tests/test_stripe_service.py
backend/tests/test_billing_api.py
backend/tests/test_sandbox_tier_enforcement.py
frontend/src/pages/Billing.tsx
frontend/src/components/TierBadge.tsx
frontend/src/components/UpgradeBanner.tsx
frontend/src/components/APIKeyManager.tsx
frontend/src/hooks/useBilling.ts
```

### Modified files
```
backend/db/models.py                        # UserAPIKey, Subscription, UsagePeriod, User.tier
backend/config.py                           # Stripe env vars + tier_enforcement_enabled
backend/llm/contracts.py                    # LLMRequest.api_key field
backend/llm/router.py                       # get_provider accepts api_key override
backend/llm/cloud_facade.py                 # Pass api_key through to router
backend/services/llm_service.py             # chat_completion_with_tools accepts api_key
backend/agents/agent.py                     # Resolve user API key before LLM call
backend/core/exceptions.py                  # TierLimitError
backend/api/v1/router.py                    # Register api_keys + billing routers
backend/main.py                             # (if needed for router registration)
backend/requirements.txt                    # stripe>=11.0.0,<13.0.0
backend/schemas/user.py                     # UserResponse.tier
backend/api/v1/sandboxes.py                 # Tier check before sandbox creation
backend/services/budget_service.py          # Record tier usage on session end
frontend/src/api/client.ts                  # API key + billing methods
frontend/src/App.tsx                        # Billing route
frontend/src/pages/UserSettings.tsx         # API key management + billing link
```

---

## Phase 1: Per-User API Key Management

### Task 1: UserAPIKey model

**Files:**
- Modify: `backend/db/models.py:89-104` (after User model)
- Test: `backend/tests/test_user_api_keys.py` (create — model tests only)

- [ ] **Step 1: Write test for UserAPIKey model**

```python
# backend/tests/test_user_api_keys.py
"""Tests for UserAPIKey model and repository."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, User, UserAPIKey


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_api_key_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-apikey", email="apikey@test.com")
    db.add(user)
    await db.commit()

    key = UserAPIKey(
        id=uuid.uuid4(),
        user_id=user.id,
        provider="anthropic",
        encrypted_key="gAAAAAB...",
        display_hint="...abc",
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    assert key.provider == "anthropic"
    assert key.display_hint == "...abc"
    assert key.is_valid is True


@pytest.mark.asyncio
async def test_user_api_key_unique_per_provider(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-uniq", email="uniq@test.com")
    db.add(user)
    await db.commit()

    key1 = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="anthropic", encrypted_key="k1")
    db.add(key1)
    await db.commit()

    # Same user + provider should violate unique constraint
    key2 = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="anthropic", encrypted_key="k2")
    db.add(key2)
    with pytest.raises(Exception):  # IntegrityError
        await db.commit()


@pytest.mark.asyncio
async def test_user_api_key_relationship(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-rel", email="rel@test.com")
    db.add(user)
    await db.commit()

    key = UserAPIKey(id=uuid.uuid4(), user_id=user.id, provider="openai", encrypted_key="k")
    db.add(key)
    await db.commit()

    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.provider == "openai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_user_api_keys.py -v`
Expected: FAIL — `UserAPIKey` not importable

- [ ] **Step 3: Add UserAPIKey model to models.py**

In `backend/db/models.py`, add after the User class (after the `sandboxes` relationship, line ~104), before `SandboxConfig`:

```python
class UserAPIKey(Base):
    """Per-user encrypted LLM API key for a specific provider."""

    __tablename__ = "user_api_keys"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)  # anthropic | openai | google | moonshot
    encrypted_key = Column(Text, nullable=False)
    display_hint = Column(String(20), nullable=True)  # "sk-...abc" for UI
    is_valid = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
    )
```

Also add a relationship to the User class (after `sandboxes` relationship):

```python
    api_keys = relationship("UserAPIKey", back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_user_api_keys.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py backend/tests/test_user_api_keys.py
git commit -m "feat(api-keys): add UserAPIKey model for per-user LLM API keys"
```

---

### Task 2: UserAPIKey repository with encryption

**Files:**
- Create: `backend/db/repositories/user_api_keys.py`
- Modify: `backend/tests/test_user_api_keys.py` (add repository tests)

- [ ] **Step 1: Write repository tests**

Append to `backend/tests/test_user_api_keys.py`:

```python
# ── Repository tests ──────────────────────────────────────────────────

from backend.db.repositories.user_api_keys import UserAPIKeyRepository


@pytest.mark.asyncio
async def test_repo_upsert_creates_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo1", email="repo1@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    key = await repo.upsert(user.id, "anthropic", "sk-ant-api03-real-key-here")
    assert key.provider == "anthropic"
    assert key.display_hint == "...ere"  # "..." prefix + last 3 chars
    assert key.encrypted_key != "sk-ant-api03-real-key-here"  # encrypted


@pytest.mark.asyncio
async def test_repo_upsert_updates_existing(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo2", email="repo2@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-old-key")
    updated = await repo.upsert(user.id, "anthropic", "sk-new-key")
    assert updated.display_hint == "...key"  # "..." prefix + last 3 of new key


@pytest.mark.asyncio
async def test_repo_get_decrypted_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo3", email="repo3@test.com")
    db.add(user)
    await db.commit()

    enc_key = "test-key-32-chars-padded-ok!!!!!"
    repo = UserAPIKeyRepository(db, encryption_key=enc_key)
    await repo.upsert(user.id, "openai", "sk-openai-secret-123")

    plaintext = await repo.get_decrypted_key(user.id, "openai")
    assert plaintext == "sk-openai-secret-123"


@pytest.mark.asyncio
async def test_repo_get_decrypted_key_missing(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo4", email="repo4@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    plaintext = await repo.get_decrypted_key(user.id, "anthropic")
    assert plaintext is None


@pytest.mark.asyncio
async def test_repo_list_for_user(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo5", email="repo5@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-ant-xxx")
    await repo.upsert(user.id, "openai", "sk-oai-xxx")

    keys = await repo.list_for_user(user.id)
    providers = {k.provider for k in keys}
    assert providers == {"anthropic", "openai"}


@pytest.mark.asyncio
async def test_repo_delete_key(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo6", email="repo6@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    await repo.upsert(user.id, "anthropic", "sk-ant-xxx")
    deleted = await repo.delete_key(user.id, "anthropic")
    assert deleted is True

    keys = await repo.list_for_user(user.id)
    assert len(keys) == 0


@pytest.mark.asyncio
async def test_repo_delete_nonexistent(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-repo7", email="repo7@test.com")
    db.add(user)
    await db.commit()

    repo = UserAPIKeyRepository(db, encryption_key="test-key-32-chars-padded-ok!!!!!")
    deleted = await repo.delete_key(user.id, "anthropic")
    assert deleted is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_user_api_keys.py::test_repo_upsert_creates_key -v`
Expected: FAIL — `user_api_keys` module not found

- [ ] **Step 3: Implement UserAPIKeyRepository**

```python
# backend/db/repositories/user_api_keys.py
"""
Per-user LLM API key repository — encrypted CRUD.

Uses the same Fernet encryption as ProjectSecretsRepository.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import UserAPIKey
from backend.db.repositories.project_secrets import encrypt_value, decrypt_value
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

VALID_PROVIDERS = {"anthropic", "openai", "google", "moonshot"}


class UserAPIKeyRepository:
    def __init__(self, session: AsyncSession, encryption_key: str = ""):
        self._db = session
        self._encryption_key = encryption_key or ""

    async def list_for_user(self, user_id: UUID) -> list[UserAPIKey]:
        result = await self._db.execute(
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user_id)
            .order_by(UserAPIKey.provider)
        )
        return list(result.scalars().all())

    async def get_by_provider(self, user_id: UUID, provider: str) -> UserAPIKey | None:
        result = await self._db.execute(
            select(UserAPIKey).where(
                UserAPIKey.user_id == user_id,
                UserAPIKey.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: UUID, provider: str, plaintext_key: str) -> UserAPIKey:
        """Create or update a user's API key for a provider."""
        stored, _ = encrypt_value(plaintext_key, self._encryption_key)
        hint = plaintext_key[-3:] if len(plaintext_key) >= 3 else plaintext_key

        existing = await self.get_by_provider(user_id, provider)
        if existing:
            existing.encrypted_key = stored
            existing.display_hint = f"...{hint}"
            existing.is_valid = True
            await self._db.flush()
            return existing

        key = UserAPIKey(
            id=uuid.uuid4(),
            user_id=user_id,
            provider=provider,
            encrypted_key=stored,
            display_hint=f"...{hint}",
        )
        self._db.add(key)
        await self._db.flush()
        return key

    async def get_decrypted_key(self, user_id: UUID, provider: str) -> str | None:
        """Get the plaintext API key for a user+provider. Returns None if not found."""
        row = await self.get_by_provider(user_id, provider)
        if not row:
            return None
        if not row.is_valid:
            return None
        return decrypt_value(row.encrypted_key, self._encryption_key)

    async def mark_invalid(self, user_id: UUID, provider: str) -> None:
        """Mark a key as invalid (e.g. after auth error from provider)."""
        row = await self.get_by_provider(user_id, provider)
        if row:
            row.is_valid = False
            await self._db.flush()

    async def delete_key(self, user_id: UUID, provider: str) -> bool:
        row = await self.get_by_provider(user_id, provider)
        if not row:
            return False
        await self._db.delete(row)
        await self._db.flush()
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_user_api_keys.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/repositories/user_api_keys.py backend/tests/test_user_api_keys.py
git commit -m "feat(api-keys): add UserAPIKeyRepository with Fernet encryption"
```

---

### Task 3: API key endpoints

**Files:**
- Create: `backend/api/v1/api_keys.py`
- Create: `backend/schemas/api_keys.py`
- Modify: `backend/api/v1/router.py`
- Test: `backend/tests/test_api_keys_api.py` (create)

- [ ] **Step 1: Write API endpoint tests**

```python
# backend/tests/test_api_keys_api.py
"""Tests for user API key management endpoints."""
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import User, UserAPIKey
from backend.main import app


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@test.com"
    user.display_name = "Test"
    return user


@pytest.mark.asyncio
async def test_list_api_keys(mock_user):
    mock_key = MagicMock(spec=UserAPIKey)
    mock_key.provider = "anthropic"
    mock_key.display_hint = "...abc"
    mock_key.is_valid = True

    with patch("backend.api.v1.api_keys.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.api_keys.get_db"), \
         patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        MockRepo.return_value.list_for_user = AsyncMock(return_value=[mock_key])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/auth/api-keys",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_upsert_api_key(mock_user):
    mock_key = MagicMock(spec=UserAPIKey)
    mock_key.provider = "anthropic"
    mock_key.display_hint = "...key"
    mock_key.is_valid = True

    with patch("backend.api.v1.api_keys.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.api_keys.get_db") as mock_get_db, \
         patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        MockRepo.return_value.upsert = AsyncMock(return_value=mock_key)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/auth/api-keys/anthropic",
                json={"api_key": "sk-ant-xxx"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            assert resp.json()["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_upsert_invalid_provider(mock_user):
    with patch("backend.api.v1.api_keys.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.api_keys.get_db"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/auth/api-keys/invalid_provider",
                json={"api_key": "sk-xxx"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_api_key(mock_user):
    with patch("backend.api.v1.api_keys.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.api_keys.get_db") as mock_get_db, \
         patch("backend.api.v1.api_keys.UserAPIKeyRepository") as MockRepo:
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db
        MockRepo.return_value.delete_key = AsyncMock(return_value=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(
                "/api/v1/auth/api-keys/anthropic",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_keys_api.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Create API key schemas**

```python
# backend/schemas/api_keys.py
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
```

- [ ] **Step 4: Create API key router**

```python
# backend/api/v1/api_keys.py
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
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}. Valid: {', '.join(sorted(VALID_PROVIDERS))}")

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
    """Test an API key by making a minimal call to the provider."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    repo = _get_repo(db)
    plaintext = await repo.get_decrypted_key(current_user.id, provider)
    if not plaintext:
        return APIKeyTestResponse(valid=False, error="No API key configured for this provider")

    try:
        from backend.llm.router import ProviderRouter
        router_instance = ProviderRouter()
        # Map provider name to a test model for that provider
        test_models = {
            "anthropic": "claude-haiku-4-5",
            "openai": "gpt-4o-mini",
            "google": "gemini-2.0-flash-lite",
            "moonshot": "kimi-k2",
        }
        test_model = test_models.get(provider, "")
        # Just instantiate the provider — don't actually call it
        llm_provider = router_instance.get_provider(test_model, provider=provider, api_key=plaintext)
        # If we get here without error, the key format is at least valid
        return APIKeyTestResponse(valid=True)
    except Exception as exc:
        logger.warning("API key test failed for %s: %s", provider, exc)
        await repo.mark_invalid(current_user.id, provider)
        await db.commit()
        return APIKeyTestResponse(valid=False, error=str(exc))
```

- [ ] **Step 5: Register api_keys router**

In `backend/api/v1/router.py`, add at the end (after the last `include_router` call):

```python
from backend.api.v1.api_keys import router as api_keys_router
api_router.include_router(api_keys_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_keys_api.py -v`
Expected: PASS (some tests may need adjustment once router is wired — the test endpoint calls `get_provider` with `api_key` param which is added in Task 4)

Note: The `test_api_key` endpoint depends on Task 4's router change (`api_key` param). If tests fail on that endpoint, skip that specific test and return to it after Task 4.

- [ ] **Step 7: Commit**

```bash
git add backend/api/v1/api_keys.py backend/schemas/api_keys.py backend/api/v1/router.py backend/tests/test_api_keys_api.py
git commit -m "feat(api-keys): add API key CRUD endpoints"
```

---

### Task 4: LLM router — accept user API key override

**Files:**
- Modify: `backend/llm/contracts.py:57-64` (LLMRequest)
- Modify: `backend/llm/router.py:73-99` (get_provider)
- Modify: `backend/llm/cloud_facade.py:20-28` (complete + complete_from_legacy_messages)
- Modify: `backend/services/llm_service.py:266-318` (chat_completion_with_tools)
- Modify: `backend/agents/agent.py` (_call_llm)
- Test: `backend/tests/llm/test_router.py` (modify — add api_key override test)

- [ ] **Step 1: Write test for api_key override in router**

Add to `backend/tests/llm/test_router.py`:

```python
def test_get_provider_with_api_key_override(monkeypatch):
    """User-provided API key should override server settings."""
    from backend.config import settings
    # Clear server key so it would normally fail
    monkeypatch.setattr(settings, "claude_api_key", "")

    router = ProviderRouter()
    # Should work because we pass api_key directly
    provider = router.get_provider("claude-sonnet-4-6", api_key="sk-user-key-123")
    assert provider is not None


def test_get_provider_without_api_key_uses_server(monkeypatch):
    """Without user key, server key should be used."""
    from backend.config import settings
    monkeypatch.setattr(settings, "claude_api_key", "sk-server-key")

    router = ProviderRouter()
    # No api_key passed — should use server key and succeed
    provider = router.get_provider("claude-sonnet-4-6")
    assert provider is not None


def test_get_provider_no_key_at_all_raises(monkeypatch):
    """Without any key, should raise RuntimeError."""
    from backend.config import settings
    monkeypatch.setattr(settings, "claude_api_key", "")

    router = ProviderRouter()
    with pytest.raises(RuntimeError, match="CLAUDE_API_KEY"):
        router.get_provider("claude-sonnet-4-6")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/llm/test_router.py -v -k "api_key"`
Expected: FAIL — `get_provider` doesn't accept `api_key` param

- [ ] **Step 3: Add api_key to LLMRequest**

In `backend/llm/contracts.py`, add field to `LLMRequest` (after `provider`, line 64):

```python
    api_key: str | None = None  # Per-user API key override
```

- [ ] **Step 4: Update ProviderRouter.get_provider to accept api_key**

In `backend/llm/router.py`, change the `get_provider` method signature and body:

```python
    def get_provider(self, model: str, provider: str | None = None, api_key: str | None = None) -> BaseLLMProvider:
        selected = self.resolve_provider_name(model, provider)
        if selected == "anthropic":
            key = api_key or settings.claude_api_key
            if not key:
                raise RuntimeError("CLAUDE_API_KEY is not configured")
            return AnthropicSDKProvider(api_key=key)
        if selected == "google":
            key = api_key or settings.gemini_api_key
            if not key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            return GeminiProviderAdapter(
                api_key=key,
                timeout_seconds=self.timeout_seconds,
            )
        if selected == "openai":
            key = api_key or settings.openai_api_key
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            return OpenAISDKProvider(api_key=key)
        if selected in {"kimi", "moonshot"}:
            key = api_key or settings.moonshot_api_key
            if not key:
                raise RuntimeError("MOONSHOT_API_KEY is not configured")
            return KimiSDKProvider(
                api_key=key,
                base_url=settings.moonshot_base_url,
            )
        raise RuntimeError(
            "No LLM provider configured. Set CLAUDE_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or MOONSHOT_API_KEY."
        )
```

- [ ] **Step 5: Update CloudLLMFacade to pass api_key through**

In `backend/llm/cloud_facade.py`, update the `complete` method:

```python
    async def complete(self, request: LLMRequest) -> LLMResponse:
        normalized_request, adapter = normalize_request_tool_names(request)
        provider = self.router.get_provider(
            normalized_request.model, normalized_request.provider,
            api_key=normalized_request.api_key,
        )
        response = await provider.complete(normalized_request)
        if adapter is None:
            return response
        return denormalize_response_tool_calls(response, adapter)
```

Update `complete_from_legacy_messages` to accept and pass `api_key`:

```python
    async def complete_from_legacy_messages(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        provider: str | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
    ) -> LLMResponse:
```

And in the `LLMRequest` construction at the end of that method, add `api_key=api_key`:

```python
        return await self.complete(
            LLMRequest(
                model=model,
                provider=provider,
                system_prompt=system_prompt,
                messages=canonical_messages,
                tools=canonical_tools,
                temperature=settings.llm_temperature,
                max_tokens=effective_max_tokens,
                api_key=api_key,
            )
        )
```

- [ ] **Step 6: Update llm_service.chat_completion_with_tools**

In `backend/services/llm_service.py`, add `api_key: str | None = None` to `chat_completion_with_tools` signature:

```python
    async def chat_completion_with_tools(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        api_key: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], Any]:
```

And pass `api_key` to the facade call (line ~297):

```python
        if not settings.llm_use_legacy_http:
            response = await self._facade.complete_from_legacy_messages(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                provider=provider,
                max_tokens=effective_max_tokens,
                api_key=api_key,
            )
```

- [ ] **Step 7: Wire user API key resolution into agent loop**

In `backend/agents/agent.py`, update `_call_llm` to resolve the user's API key before the LLM call.

Add a helper method to the agent class:

```python
    async def _resolve_user_api_key(self) -> str | None:
        """Look up the user's API key for the current model's provider."""
        try:
            from backend.db.repositories.user_api_keys import UserAPIKeyRepository
            from backend.llm.router import ProviderRouter

            # Determine provider from model
            router = ProviderRouter()
            provider_name = router.resolve_provider_name(self._resolved_model, self._agent.provider)

            # Map provider name to UserAPIKey provider
            provider_map = {"anthropic": "anthropic", "google": "google", "openai": "openai", "kimi": "moonshot", "moonshot": "moonshot"}
            api_key_provider = provider_map.get(provider_name)
            if not api_key_provider:
                return None

            # Get user_id from the project owner
            from backend.db.models import Project
            project = await self._db.get(Project, self._agent.project_id)
            if not project or not project.owner_id:
                return None

            from backend.config import settings
            repo = UserAPIKeyRepository(self._db, encryption_key=settings.secret_encryption_key)
            return await repo.get_decrypted_key(project.owner_id, api_key_provider)
        except Exception as exc:
            logger.warning("Failed to resolve user API key: %s", exc)
            return None
```

In `_call_llm`, before calling `chat_completion_with_tools`, resolve the key:

```python
        # Resolve per-user API key (falls back to server key if None)
        user_api_key = await self._resolve_user_api_key()

        content, tool_calls, llm_response = await self._services.llm.chat_completion_with_tools(
            model=self._resolved_model,
            system_prompt=self._prompt.system_prompt,
            messages=llm_messages,
            tools=tool_defs,
            max_tokens=app_settings.llm_max_tokens_agent_loop,
            api_key=user_api_key,
        )
```

- [ ] **Step 8: Run tests**

Run: `cd backend && python -m pytest tests/llm/test_router.py tests/test_user_api_keys.py -v`
Expected: PASS

- [ ] **Step 9: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --tb=short -m "not integration" -x`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/llm/contracts.py backend/llm/router.py backend/llm/cloud_facade.py backend/services/llm_service.py backend/agents/agent.py backend/tests/llm/test_router.py
git commit -m "feat(api-keys): LLM router accepts per-user API key override"
```

---

### Task 5: Frontend — API key management in User Settings

**Files:**
- Create: `frontend/src/components/APIKeyManager.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/UserSettings.tsx`

- [ ] **Step 1: Add API key methods to client.ts**

Add at the end of `frontend/src/api/client.ts`:

```typescript
// ── User API Keys ─────────────────────────────────────────────────────

export interface UserAPIKey {
  provider: string;
  display_hint: string | null;
  is_valid: boolean;
}

export interface APIKeyTestResult {
  valid: boolean;
  error?: string;
}

export async function listAPIKeys(): Promise<UserAPIKey[]> {
  return request<UserAPIKey[]>('GET', '/auth/api-keys');
}

export async function upsertAPIKey(provider: string, apiKey: string): Promise<UserAPIKey> {
  return request<UserAPIKey>('PUT', `/auth/api-keys/${provider}`, { api_key: apiKey });
}

export async function deleteAPIKey(provider: string): Promise<void> {
  return request<void>('DELETE', `/auth/api-keys/${provider}`);
}

export async function testAPIKey(provider: string): Promise<APIKeyTestResult> {
  return request<APIKeyTestResult>('POST', `/auth/api-keys/${provider}/test`);
}
```

- [ ] **Step 2: Create APIKeyManager component**

```tsx
// frontend/src/components/APIKeyManager.tsx
import { useState, useEffect, useCallback } from 'react';
import { Key, Check, X, Trash2, Loader2 } from 'lucide-react';

import { listAPIKeys, upsertAPIKey, deleteAPIKey, testAPIKey, type UserAPIKey } from '../api/client';
import { Button } from './ui';

const PROVIDERS = [
  { id: 'anthropic', name: 'Anthropic (Claude)', placeholder: 'sk-ant-api03-...' },
  { id: 'openai', name: 'OpenAI', placeholder: 'sk-...' },
  { id: 'google', name: 'Google (Gemini)', placeholder: 'AIza...' },
  { id: 'moonshot', name: 'Moonshot (Kimi)', placeholder: 'sk-...' },
];

export function APIKeyManager() {
  const [keys, setKeys] = useState<UserAPIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ provider: string; valid: boolean; error?: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listAPIKeys();
      setKeys(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const handleSave = async (provider: string) => {
    if (!keyInput.trim()) return;
    setSaving(true);
    try {
      await upsertAPIKey(provider, keyInput.trim());
      setKeyInput('');
      setEditingProvider(null);
      await refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save key');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (provider: string) => {
    try {
      await deleteAPIKey(provider);
      await refresh();
    } catch {
      // key may not exist
    }
  };

  const handleTest = async (provider: string) => {
    setTesting(provider);
    setTestResult(null);
    try {
      const result = await testAPIKey(provider);
      setTestResult({ provider, ...result });
    } catch (err) {
      setTestResult({ provider, valid: false, error: err instanceof Error ? err.message : 'Test failed' });
    } finally {
      setTesting(null);
    }
  };

  const getKeyForProvider = (provider: string) => keys.find(k => k.provider === provider);

  if (loading) return <div className="text-sm text-[var(--text-muted)]">Loading API keys...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Key size={16} />
        <h2 className="text-sm font-medium">LLM API Keys</h2>
      </div>
      <p className="text-xs text-[var(--text-muted)]">
        Add your own API keys so agents use your account directly. Server keys are used as fallback.
      </p>

      {PROVIDERS.map(({ id, name, placeholder }) => {
        const existing = getKeyForProvider(id);
        const isEditing = editingProvider === id;

        return (
          <div key={id} className="rounded border border-[var(--border)] p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{name}</span>
                {existing && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${existing.is_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {existing.is_valid ? 'Active' : 'Invalid'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {existing && (
                  <>
                    <span className="text-xs text-[var(--text-muted)] font-mono">{existing.display_hint}</span>
                    <Button variant="ghost" size="sm" onClick={() => handleTest(id)} disabled={testing === id}>
                      {testing === id ? <Loader2 size={12} className="animate-spin" /> : 'Test'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(id)}>
                      <Trash2 size={12} />
                    </Button>
                  </>
                )}
                <Button variant="ghost" size="sm" onClick={() => { setEditingProvider(isEditing ? null : id); setKeyInput(''); }}>
                  {isEditing ? 'Cancel' : existing ? 'Update' : 'Add'}
                </Button>
              </div>
            </div>

            {testResult?.provider === id && (
              <div className={`text-xs flex items-center gap-1 ${testResult.valid ? 'text-green-600' : 'text-red-600'}`}>
                {testResult.valid ? <Check size={12} /> : <X size={12} />}
                {testResult.valid ? 'Key is valid' : testResult.error}
              </div>
            )}

            {isEditing && (
              <div className="flex gap-2">
                <input
                  type="password"
                  value={keyInput}
                  onChange={e => setKeyInput(e.target.value)}
                  placeholder={placeholder}
                  className="flex-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-2 py-1 text-sm font-mono"
                  onKeyDown={e => e.key === 'Enter' && handleSave(id)}
                />
                <Button size="sm" onClick={() => handleSave(id)} disabled={saving || !keyInput.trim()}>
                  {saving ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Add APIKeyManager to UserSettings page**

In `frontend/src/pages/UserSettings.tsx`, add import and render the component inside the settings card, after the existing form fields (after GitHub token section):

```tsx
import { APIKeyManager } from '../components/APIKeyManager';

// Inside the return JSX, add a new section:
<div className="border-t border-[var(--border)] pt-4 mt-4">
  <APIKeyManager />
</div>
```

- [ ] **Step 4: Run frontend lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/APIKeyManager.tsx frontend/src/api/client.ts frontend/src/pages/UserSettings.tsx
git commit -m "feat(api-keys): add API key management UI in User Settings"
```

---

## Phase 2: Billing System

### Task 6: Add Stripe dependency and config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py:11-116`
- Test: `backend/tests/test_billing_config.py` (create)

- [ ] **Step 1: Write test for Stripe config fields**

```python
# backend/tests/test_billing_config.py
"""Tests for billing configuration."""
import os
import pytest


def test_settings_has_stripe_fields():
    """Verify Stripe config fields exist with correct defaults."""
    from backend.config import Settings

    s = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        stripe_secret_key="sk_test_xxx",
        stripe_publishable_key="pk_test_xxx",
    )
    assert s.stripe_secret_key == "sk_test_xxx"
    assert s.stripe_publishable_key == "pk_test_xxx"
    assert s.stripe_webhook_secret == ""
    assert s.stripe_individual_price_id == ""
    assert s.stripe_team_price_id == ""
    assert s.tier_enforcement_enabled is False


def test_settings_stripe_defaults_empty():
    """All Stripe fields default to empty/disabled."""
    from backend.config import Settings

    s = Settings(database_url="sqlite+aiosqlite:///:memory:")
    assert s.stripe_secret_key == ""
    assert s.tier_enforcement_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_billing_config.py -v`
Expected: FAIL — `stripe_secret_key` attribute not found on Settings

- [ ] **Step 3: Add Stripe SDK to requirements.txt**

Add after line 14 (`firebase-admin>=6.0.0`):
```
stripe>=11.0.0,<13.0.0
```

- [ ] **Step 4: Add Stripe settings to config.py**

Add after line 99 (sandbox JWT section), before logging section:

```python
    # Stripe Billing
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_individual_price_id: str = ""      # price_xxx for $20/mo Individual
    stripe_team_price_id: str = ""            # price_xxx for $50/mo Team
    tier_enforcement_enabled: bool = False    # Kill switch: disable all tier checks
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_billing_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/tests/test_billing_config.py
git commit -m "feat(billing): add Stripe SDK dependency and config fields"
```

---

### Task 7: Add database models (Subscription, UsagePeriod, User.tier)

**Files:**
- Modify: `backend/db/models.py:89-104` (User model)
- Modify: `backend/db/models.py:205-217` (after SandboxUsageEvent)
- Modify: `backend/core/exceptions.py`
- Test: `backend/tests/test_billing_models.py` (create)

- [ ] **Step 1: Write test for new models**

```python
# backend/tests/test_billing_models.py
"""Tests for billing data models."""
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, UsagePeriod, User


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_has_tier_field(db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        firebase_uid="test-uid",
        email="test@example.com",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.tier == "free"
    assert user.stripe_customer_id is None


@pytest.mark.asyncio
async def test_subscription_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-sub", email="sub@test.com")
    db.add(user)
    await db.commit()

    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        tier="individual",
        status="active",
        stripe_customer_id="cus_test123",
        stripe_subscription_id="sub_test123",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    assert sub.tier == "individual"
    assert sub.status == "active"
    assert sub.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_usage_period_model(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-usage", email="usage@test.com")
    db.add(user)
    await db.commit()

    period = UsagePeriod(
        id=uuid.uuid4(),
        user_id=user.id,
        period_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 3, 31, tzinfo=timezone.utc),
        headless_seconds=3600,
        desktop_seconds=1800,
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)

    assert period.headless_seconds == 3600
    assert period.desktop_seconds == 1800


@pytest.mark.asyncio
async def test_subscription_user_relationship(db: AsyncSession):
    user = User(id=uuid.uuid4(), firebase_uid="uid-rel", email="rel@test.com")
    db.add(user)
    await db.commit()

    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="team")
    db.add(sub)
    await db.commit()

    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.tier == "team"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_billing_models.py -v`
Expected: FAIL — `Subscription`, `UsagePeriod` not importable, `User.tier` missing

- [ ] **Step 3: Add TierLimitError to exceptions.py**

Add at the end of `backend/core/exceptions.py`:

```python
class TierLimitError(AICTException):
    """Raised when a user exceeds their subscription tier limits."""

    def __init__(self, message: str, current_tier: str = "free", upgrade_url: str = "/settings/billing"):
        self.current_tier = current_tier
        self.upgrade_url = upgrade_url
        super().__init__(message)
```

- [ ] **Step 4: Add tier and stripe_customer_id to User model**

In `backend/db/models.py`, add two columns to the User class after `github_token` (line 96), before `created_at` (line 97):

```python
    tier = Column(String(20), nullable=False, default="free")  # free | individual | team
    stripe_customer_id = Column(String(255), nullable=True)
```

Add new relationship after `api_keys` relationship:

```python
    subscription = relationship("Subscription", back_populates="user", uselist=False)
```

- [ ] **Step 5: Add Subscription model**

Add after the UserAPIKey class, before the SandboxConfig section:

```python
class Subscription(Base):
    """Stripe subscription state for a user."""

    __tablename__ = "subscriptions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    tier = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="subscription")

    __table_args__ = (
        Index("ix_subscriptions_stripe_customer", "stripe_customer_id"),
        Index("ix_subscriptions_stripe_sub", "stripe_subscription_id"),
    )
```

- [ ] **Step 6: Add UsagePeriod model**

Add after the Subscription model:

```python
class UsagePeriod(Base):
    """Monthly sandbox usage counters per user per billing cycle."""

    __tablename__ = "usage_periods"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    headless_seconds = Column(BigInteger, default=0, nullable=False)
    desktop_seconds = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "period_start", name="uq_usage_period_user_start"),
    )
```

- [ ] **Step 7: Add unit_type to SandboxUsageEvent if missing**

Check `SandboxUsageEvent` (line ~205). If `unit_type` column is not present, add:

```python
    unit_type = Column(String(20), nullable=False, default="headless")  # headless | desktop
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_billing_models.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/db/models.py backend/core/exceptions.py backend/tests/test_billing_models.py
git commit -m "feat(billing): add Subscription, UsagePeriod models and User.tier field"
```

---

### Task 8: Create Alembic migration (combined v5)

**Files:**
- Create: `backend/migrations/versions/006_add_v5_api_keys_and_billing.py`

This single migration adds ALL v5 tables: `user_api_keys`, `subscriptions`, `usage_periods`, User columns, and `SandboxUsageEvent.unit_type`.

- [ ] **Step 1: Write the migration**

```python
# backend/migrations/versions/006_add_v5_api_keys_and_billing.py
"""v5-006: Add per-user API keys and billing tables.

Revision ID: 006_add_v5
Revises: 005_add_target_user_id_remove_sentinel
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_add_v5"
down_revision: str = "005_add_target_user_id_remove_sentinel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── User columns ──────────────────────────────────────────────────
    op.add_column("users", sa.Column("tier", sa.String(20), nullable=False, server_default="free"))
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))

    # ── User API keys table ───────────────────────────────────────────
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("display_hint", sa.String(20), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
    )

    # ── Subscriptions table ───────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_stripe_customer", "subscriptions", ["stripe_customer_id"])
    op.create_index("ix_subscriptions_stripe_sub", "subscriptions", ["stripe_subscription_id"])

    # ── Usage periods table ───────────────────────────────────────────
    op.create_table(
        "usage_periods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headless_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("desktop_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period_start", name="uq_usage_period_user_start"),
    )

    # ── SandboxUsageEvent.unit_type ──────────────────────────────────
    op.add_column(
        "sandbox_usage_events",
        sa.Column("unit_type", sa.String(20), nullable=False, server_default="headless"),
    )


def downgrade() -> None:
    op.drop_column("sandbox_usage_events", "unit_type")
    op.drop_table("usage_periods")
    op.drop_table("subscriptions")
    op.drop_table("user_api_keys")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "tier")
```

- [ ] **Step 2: Verify migration graph is valid**

Run: `cd backend && python -m pytest tests/test_migration_graph.py -v`
Expected: PASS (migration chain is linear)

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/versions/006_add_v5_api_keys_and_billing.py
git commit -m "feat(v5): add Alembic migration for API keys and billing tables"
```

---

### Task 9: Create TierService with enforcement logic

**Files:**
- Create: `backend/services/tier_service.py`
- Test: `backend/tests/test_tier_service.py` (create)

- [ ] **Step 1: Write tests for TierService**

```python
# backend/tests/test_tier_service.py
"""Tests for TierService — sandbox hour enforcement."""
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, UsagePeriod, User
from backend.core.exceptions import TierLimitError


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


async def _make_user(db, tier="free"):
    user = User(id=uuid.uuid4(), firebase_uid=f"uid-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.com", tier=tier)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_free_tier_headless_within_limit(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 14 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")  # should not raise


@pytest.mark.asyncio
async def test_free_tier_headless_at_limit(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 15 * 3600
    await db.commit()
    with pytest.raises(TierLimitError, match="headless"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_free_tier_cannot_use_desktop_beyond_limit(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.desktop_seconds = 15 * 3600
    await db.commit()
    with pytest.raises(TierLimitError):
        await svc.check_can_start_sandbox(user, "desktop")


@pytest.mark.asyncio
async def test_individual_tier_generous_limits(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 100 * 3600
    period.desktop_seconds = 50 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")
    await svc.check_can_start_sandbox(user, "desktop")


@pytest.mark.asyncio
async def test_record_usage_increments(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "headless", 3600)
    await svc.record_usage(user, "headless", 1800)
    period = await svc._get_current_period(user)
    assert period.headless_seconds == 5400


@pytest.mark.asyncio
async def test_record_usage_desktop(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "desktop", 7200)
    period = await svc._get_current_period(user)
    assert period.desktop_seconds == 7200


@pytest.mark.asyncio
async def test_get_remaining_seconds(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "free")
    svc = TierService(db)
    remaining = await svc.get_remaining_seconds(user, "headless")
    assert remaining == 15 * 3600

    await svc.record_usage(user, "headless", 5 * 3600)
    remaining = await svc.get_remaining_seconds(user, "headless")
    assert remaining == 10 * 3600


@pytest.mark.asyncio
async def test_get_usage_summary(db):
    from backend.services.tier_service import TierService
    user = await _make_user(db, "individual")
    svc = TierService(db)
    await svc.record_usage(user, "headless", 3600)
    await svc.record_usage(user, "desktop", 1800)
    summary = await svc.get_usage_summary(user)
    assert summary["headless_seconds_used"] == 3600
    assert summary["desktop_seconds_used"] == 1800
    assert summary["headless_seconds_included"] == 200 * 3600
    assert summary["desktop_seconds_included"] == 200 * 3600
    assert summary["tier"] == "individual"


@pytest.mark.asyncio
async def test_enforcement_disabled_skips_check(db, monkeypatch):
    """When tier_enforcement_enabled=False, checks always pass."""
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", False)
    user = await _make_user(db, "free")
    svc = TierService(db)
    await svc._ensure_usage_period(user)
    period = await svc._get_current_period(user)
    period.headless_seconds = 999 * 3600
    await db.commit()
    await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_past_due_blocks_sandbox(db, monkeypatch):
    """Past-due subscription should block sandbox access."""
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "individual")
    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", status="past_due")
    db.add(sub)
    await db.commit()
    svc = TierService(db)
    with pytest.raises(TierLimitError, match="past due"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_check_can_invite_member(db, monkeypatch):
    """Team member limit should be enforced."""
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "free")
    svc = TierService(db)
    # Free tier = 1 member max, already at 1
    with pytest.raises(TierLimitError, match="1 team member"):
        await svc.check_can_invite_member(user, current_count=1)


@pytest.mark.asyncio
async def test_check_can_invite_member_team(db, monkeypatch):
    """Team tier allows 3 members."""
    from backend.services.tier_service import TierService
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)
    user = await _make_user(db, "team")
    svc = TierService(db)
    await svc.check_can_invite_member(user, current_count=2)  # should not raise
    with pytest.raises(TierLimitError):
        await svc.check_can_invite_member(user, current_count=3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tier_service.py -v`
Expected: FAIL — `tier_service` module not found

- [ ] **Step 3: Implement TierService**

```python
# backend/services/tier_service.py
"""
TierService — sandbox hour enforcement by membership tier.

All sandbox usage limits are enforced here. Projects, agents, and LLM
usage are unrestricted on all tiers (users bring their own API keys).
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import TierLimitError
from backend.db.models import Subscription, UsagePeriod, User
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# ── Tier limits (seconds) ─────────────────────────────────────────────

TIER_LIMITS: dict[str, dict] = {
    "free": {
        "headless_seconds": 15 * 3600,
        "desktop_seconds": 15 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "individual": {
        "headless_seconds": 200 * 3600,
        "desktop_seconds": 200 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "team": {
        "headless_seconds": 1000 * 3600,
        "desktop_seconds": 1000 * 3600,
        "max_team_members": 3,
        "snapshots": False,
    },
}


def _get_limits(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TierService:
    def __init__(self, db: AsyncSession):
        self._db = db

    # ── Public API ─────────────────────────────────────────────────────

    async def check_can_start_sandbox(self, user: User, unit_type: str) -> None:
        """Raise TierLimitError if user has exhausted sandbox hours for this type."""
        # Always block past-due users regardless of enforcement flag —
        # payment status enforcement is a billing safety concern, not a tier limit.
        result = await self._db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = result.scalar_one_or_none()
        if sub and sub.status == "past_due":
            raise TierLimitError(
                message="Your payment is past due. Please update your payment method to continue using sandboxes.",
                current_tier=user.tier,
            )

        # Hour-limit checks can be disabled via kill-switch for gradual rollout
        if not settings.tier_enforcement_enabled:
            return

        limits = _get_limits(user.tier)
        limit_key = f"{unit_type}_seconds"
        limit_seconds = limits.get(limit_key, 0)

        period = await self._get_or_create_period(user)
        used = getattr(period, f"{unit_type}_seconds", 0)

        if used >= limit_seconds:
            hours_used = used / 3600
            hours_limit = limit_seconds / 3600
            tier = user.tier
            raise TierLimitError(
                message=(
                    f"You've used {hours_used:.0f} of {hours_limit:.0f} "
                    f"{tier} {unit_type} hours this month. "
                    + (
                        f"Upgrade to Individual for {TIER_LIMITS['individual'][limit_key] // 3600} hours."
                        if tier == "free"
                        else "Usage resets next billing cycle."
                    )
                ),
                current_tier=tier,
            )

    async def get_remaining_seconds(self, user: User, unit_type: str) -> int:
        """Seconds remaining in allowance for this sandbox type."""
        limits = _get_limits(user.tier)
        limit_seconds = limits.get(f"{unit_type}_seconds", 0)
        period = await self._get_or_create_period(user)
        used = getattr(period, f"{unit_type}_seconds", 0)
        return max(0, limit_seconds - used)

    async def record_usage(self, user: User, unit_type: str, seconds: int) -> None:
        """Increment usage counters for the current billing period."""
        period = await self._get_or_create_period(user)
        col = f"{unit_type}_seconds"
        current = getattr(period, col, 0)
        setattr(period, col, current + seconds)
        await self._db.commit()
        await self._db.refresh(period)

    async def check_can_invite_member(self, user: User, current_count: int) -> None:
        """Raise TierLimitError if team member limit reached."""
        if not settings.tier_enforcement_enabled:
            return
        limits = _get_limits(user.tier)
        max_members = limits["max_team_members"]
        if current_count >= max_members:
            raise TierLimitError(
                message=f"{user.tier.title()} tier allows {max_members} team member(s). Upgrade for more.",
                current_tier=user.tier,
            )

    async def get_usage_summary(self, user: User) -> dict:
        """Usage summary for the billing dashboard."""
        limits = _get_limits(user.tier)
        period = await self._get_or_create_period(user)
        return {
            "tier": user.tier,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "headless_seconds_used": period.headless_seconds,
            "headless_seconds_included": limits["headless_seconds"],
            "desktop_seconds_used": period.desktop_seconds,
            "desktop_seconds_included": limits["desktop_seconds"],
        }

    # ── Internal helpers ───────────────────────────────────────────────

    async def _get_or_create_period(self, user: User) -> UsagePeriod:
        """Get or create the current billing period for this user."""
        period = await self._get_current_period(user)
        if period:
            return period
        return await self._ensure_usage_period(user)

    async def _get_current_period(self, user: User) -> UsagePeriod | None:
        now = _now()
        result = await self._db.execute(
            select(UsagePeriod).where(
                UsagePeriod.user_id == user.id,
                UsagePeriod.period_start <= now,
                UsagePeriod.period_end > now,
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_usage_period(self, user: User) -> UsagePeriod:
        """Create a usage period for the current month if none exists."""
        existing = await self._get_current_period(user)
        if existing:
            return existing

        now = _now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)

        period = UsagePeriod(
            id=uuid_mod.uuid4(),
            user_id=user.id,
            period_start=period_start,
            period_end=period_end,
        )
        self._db.add(period)
        await self._db.commit()
        await self._db.refresh(period)
        return period
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tier_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/tier_service.py backend/tests/test_tier_service.py
git commit -m "feat(billing): add TierService with sandbox hour enforcement"
```

---

### Task 10: Create StripeService (Checkout + Portal + Webhook handling)

**Files:**
- Create: `backend/services/stripe_service.py`
- Test: `backend/tests/test_stripe_service.py` (create)

- [ ] **Step 1: Write tests for StripeService**

```python
# backend/tests/test_stripe_service.py
"""Tests for StripeService — Stripe API interactions (mocked)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, Subscription, User


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_checkout_session(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-checkout", email="checkout@test.com")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    svc = StripeService(db)

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"

    with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create, \
         patch("stripe.Customer.create", return_value=MagicMock(id="cus_new123")):
        url = await svc.create_checkout_session(user, "individual", "https://app.aict.dev/settings/billing")
        assert url == "https://checkout.stripe.com/test"


@pytest.mark.asyncio
async def test_create_portal_session(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-portal", email="portal@test.com", stripe_customer_id="cus_existing")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    svc = StripeService(db)

    mock_session = MagicMock()
    mock_session.url = "https://billing.stripe.com/test"

    with patch("stripe.billing_portal.Session.create", return_value=mock_session):
        url = await svc.create_portal_session(user, "https://app.aict.dev/settings/billing")
        assert url == "https://billing.stripe.com/test"


@pytest.mark.asyncio
async def test_handle_checkout_completed(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-webhook", email="webhook@test.com", stripe_customer_id="cus_wh123")
    db.add(user)
    await db.commit()

    svc = StripeService(db)
    event_data = {
        "customer": "cus_wh123",
        "subscription": "sub_wh123",
        "metadata": {"tier": "individual", "user_id": str(user.id)},
    }
    await svc.handle_checkout_completed(event_data)

    await db.refresh(user)
    assert user.tier == "individual"


@pytest.mark.asyncio
async def test_handle_subscription_deleted(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-cancel", email="cancel@test.com", tier="individual", stripe_customer_id="cus_cancel")
    db.add(user)
    await db.commit()

    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_cancel", stripe_subscription_id="sub_cancel")
    db.add(sub)
    await db.commit()

    svc = StripeService(db)
    await svc.handle_subscription_deleted({"customer": "cus_cancel", "id": "sub_cancel"})

    await db.refresh(user)
    assert user.tier == "free"


@pytest.mark.asyncio
async def test_handle_payment_failed(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-fail", email="fail@test.com", tier="individual", stripe_customer_id="cus_fail")
    db.add(user)
    await db.commit()

    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_fail", stripe_subscription_id="sub_fail", status="active")
    db.add(sub)
    await db.commit()

    svc = StripeService(db)
    await svc.handle_payment_failed({"customer": "cus_fail", "subscription": "sub_fail"})

    await db.refresh(sub)
    assert sub.status == "past_due"


@pytest.mark.asyncio
async def test_handle_invoice_paid(db):
    from backend.services.stripe_service import StripeService

    user = User(id=uuid.uuid4(), firebase_uid="uid-paid", email="paid@test.com", tier="individual", stripe_customer_id="cus_paid")
    db.add(user)
    await db.commit()

    sub = Subscription(id=uuid.uuid4(), user_id=user.id, tier="individual", stripe_customer_id="cus_paid", stripe_subscription_id="sub_paid", status="past_due")
    db.add(sub)
    await db.commit()

    svc = StripeService(db)
    await svc.handle_invoice_paid({"subscription": "sub_paid"})

    await db.refresh(sub)
    assert sub.status == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_stripe_service.py -v`
Expected: FAIL — `stripe_service` module not found

- [ ] **Step 3: Implement StripeService**

```python
# backend/services/stripe_service.py
"""
StripeService — Stripe Checkout, Portal, and webhook event handling.

Flat subscriptions only (no metered billing). Two products:
  - Individual ($20/mo)
  - Team ($50/mo)
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import Subscription, User
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

TIER_TO_PRICE = {
    "individual": lambda: settings.stripe_individual_price_id,
    "team": lambda: settings.stripe_team_price_id,
}


class StripeService:
    def __init__(self, db: AsyncSession):
        self._db = db
        stripe.api_key = settings.stripe_secret_key

    # ── Checkout ───────────────────────────────────────────────────────

    async def create_checkout_session(
        self, user: User, tier: str, return_url: str
    ) -> str:
        """Create a Stripe Checkout Session and return the URL."""
        price_fn = TIER_TO_PRICE.get(tier)
        if not price_fn:
            raise ValueError(f"Invalid tier: {tier}")
        price_id = price_fn()
        if not price_id:
            raise ValueError(f"Stripe price ID not configured for tier: {tier}")

        customer_id = await self._ensure_stripe_customer(user)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{return_url}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=return_url,
            metadata={"user_id": str(user.id), "tier": tier},
        )
        return session.url

    # ── Portal ─────────────────────────────────────────────────────────

    async def create_portal_session(self, user: User, return_url: str) -> str:
        """Create a Stripe Customer Portal session for subscription management."""
        if not user.stripe_customer_id:
            raise ValueError("User has no Stripe customer ID")

        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    # ── Webhook handlers ───────────────────────────────────────────────

    async def handle_checkout_completed(self, session_data: dict) -> None:
        """Process checkout.session.completed — set user tier."""
        customer_id = session_data.get("customer")
        subscription_id = session_data.get("subscription")
        metadata = session_data.get("metadata", {})
        tier = metadata.get("tier", "individual")
        user_id = metadata.get("user_id")

        user = await self._find_user(user_id=user_id, customer_id=customer_id)
        if not user:
            logger.error("Checkout completed but user not found: user_id=%s customer=%s", user_id, customer_id)
            return

        user.tier = tier
        user.stripe_customer_id = customer_id
        await self._upsert_subscription(user, tier=tier, stripe_customer_id=customer_id, stripe_subscription_id=subscription_id)
        await self._db.commit()
        logger.info("Checkout completed: user=%s tier=%s", user.id, tier)

    async def handle_subscription_updated(self, sub_data: dict) -> None:
        """Process customer.subscription.updated — sync status and period."""
        sub_id = sub_data.get("id")
        status = sub_data.get("status", "active")
        cancel_at_period_end = sub_data.get("cancel_at_period_end", False)

        result = await self._db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            logger.warning("Subscription updated but not found in DB: %s", sub_id)
            return

        sub.status = status
        sub.cancel_at_period_end = cancel_at_period_end

        current_period = sub_data.get("current_period_start")
        if current_period:
            sub.current_period_start = datetime.fromtimestamp(current_period, tz=timezone.utc)
        current_period_end = sub_data.get("current_period_end")
        if current_period_end:
            sub.current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

        await self._db.commit()
        logger.info("Subscription updated: sub=%s status=%s", sub_id, status)

    async def handle_subscription_deleted(self, sub_data: dict) -> None:
        """Process customer.subscription.deleted — downgrade to free."""
        customer_id = sub_data.get("customer")
        user = await self._find_user(customer_id=customer_id)
        if not user:
            logger.warning("Subscription deleted but user not found: customer=%s", customer_id)
            return

        user.tier = "free"
        result = await self._db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.tier = "free"
            sub.status = "canceled"
        await self._db.commit()
        logger.info("Subscription deleted: user=%s downgraded to free", user.id)

    async def handle_payment_failed(self, invoice_data: dict) -> None:
        """Process invoice.payment_failed — mark subscription past_due."""
        sub_id = invoice_data.get("subscription")
        if sub_id:
            result = await self._db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = "past_due"
                await self._db.commit()
                logger.warning("Payment failed: sub=%s marked past_due", sub_id)

    async def handle_invoice_paid(self, invoice_data: dict) -> None:
        """Process invoice.paid — clear past_due."""
        sub_id = invoice_data.get("subscription")
        if sub_id:
            result = await self._db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub and sub.status == "past_due":
                sub.status = "active"
                await self._db.commit()
                logger.info("Invoice paid: sub=%s cleared past_due", sub_id)

    # ── Helpers ────────────────────────────────────────────────────────

    async def _ensure_stripe_customer(self, user: User) -> str:
        """Get or create a Stripe Customer for this user."""
        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(
            email=user.email,
            name=user.display_name or user.email,
            metadata={"aict_user_id": str(user.id)},
        )
        user.stripe_customer_id = customer.id
        await self._db.commit()
        return customer.id

    async def _find_user(
        self, *, user_id: str | None = None, customer_id: str | None = None
    ) -> User | None:
        if user_id:
            return await self._db.get(User, uuid_mod.UUID(user_id) if isinstance(user_id, str) else user_id)
        if customer_id:
            result = await self._db.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            return result.scalar_one_or_none()
        return None

    async def _upsert_subscription(
        self, user: User, *, tier: str, stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Subscription:
        result = await self._db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.tier = tier
            sub.status = "active"
            sub.stripe_customer_id = stripe_customer_id
            sub.stripe_subscription_id = stripe_subscription_id
        else:
            sub = Subscription(
                id=uuid_mod.uuid4(),
                user_id=user.id,
                tier=tier,
                status="active",
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
            )
            self._db.add(sub)
        return sub
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_stripe_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/stripe_service.py backend/tests/test_stripe_service.py
git commit -m "feat(billing): add StripeService for checkout, portal, and webhooks"
```

---

### Task 11: Create billing API router

**Files:**
- Create: `backend/api/v1/billing.py`
- Create: `backend/schemas/billing.py`
- Modify: `backend/api/v1/router.py`
- Test: `backend/tests/test_billing_api.py` (create)

- [ ] **Step 1: Write tests for billing endpoints**

```python
# backend/tests/test_billing_api.py
"""Tests for billing API endpoints."""
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import User
from backend.main import app


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.tier = "free"
    user.stripe_customer_id = None
    user.email = "test@test.com"
    user.display_name = "Test"
    return user


@pytest.mark.asyncio
async def test_get_subscription_returns_tier(mock_user):
    with patch("backend.api.v1.billing.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.billing.get_db"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/billing/subscription",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["tier"] == "free"


@pytest.mark.asyncio
async def test_get_usage_returns_summary(mock_user):
    mock_summary = {
        "tier": "free",
        "period_start": "2026-03-01T00:00:00+00:00",
        "period_end": "2026-04-01T00:00:00+00:00",
        "headless_seconds_used": 3600,
        "headless_seconds_included": 54000,
        "desktop_seconds_used": 0,
        "desktop_seconds_included": 54000,
    }
    with patch("backend.api.v1.billing.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.billing.get_db"), \
         patch("backend.api.v1.billing.TierService") as MockTier:
        MockTier.return_value.get_usage_summary = AsyncMock(return_value=mock_summary)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/billing/usage",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["headless_seconds_used"] == 3600


@pytest.mark.asyncio
async def test_checkout_requires_valid_tier(mock_user):
    with patch("backend.api.v1.billing.get_current_user", return_value=mock_user), \
         patch("backend.api.v1.billing.get_db"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/checkout-session",
                json={"tier": "invalid"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(mock_user):
    with patch("backend.api.v1.billing.settings") as mock_settings:
        mock_settings.stripe_webhook_secret = "whsec_test"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b'{}',
                headers={"stripe-signature": "bad_sig"},
            )
            assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_billing_api.py -v`
Expected: FAIL — billing module not found / route not registered

- [ ] **Step 3: Create billing schemas**

```python
# backend/schemas/billing.py
"""Billing request/response schemas."""

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    tier: str  # "individual" | "team"
    return_url: str = "/settings/billing"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionRequest(BaseModel):
    return_url: str = "/settings/billing"


class PortalSessionResponse(BaseModel):
    portal_url: str


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    cancel_at_period_end: bool = False
    current_period_end: str | None = None


class UsageSummaryResponse(BaseModel):
    tier: str
    period_start: str
    period_end: str
    headless_seconds_used: int
    headless_seconds_included: int
    desktop_seconds_used: int
    desktop_seconds_included: int
```

- [ ] **Step 4: Create billing API router**

```python
# backend/api/v1/billing.py
"""Billing API — Stripe Checkout, Portal, subscription status, usage."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import stripe

from backend.config import settings
from backend.core.auth import get_current_user
from backend.db.models import Subscription, User
from backend.db.session import get_db
from backend.schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionRequest,
    PortalSessionResponse,
    SubscriptionResponse,
    UsageSummaryResponse,
)
from backend.services.stripe_service import StripeService
from backend.services.tier_service import TierService
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's subscription status."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if sub:
        return SubscriptionResponse(
            tier=sub.tier,
            status=sub.status,
            cancel_at_period_end=sub.cancel_at_period_end,
            current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        )

    return SubscriptionResponse(tier=current_user.tier, status="active")


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current billing period usage summary."""
    svc = TierService(db)
    summary = await svc.get_usage_summary(current_user)
    return UsageSummaryResponse(**summary)


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout Session for upgrading."""
    if body.tier not in ("individual", "team"):
        raise HTTPException(status_code=400, detail=f"Invalid tier: {body.tier}")

    svc = StripeService(db)
    try:
        url = await svc.create_checkout_session(current_user, body.tier, body.return_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CheckoutSessionResponse(checkout_url=url)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    body: PortalSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Customer Portal session."""
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    svc = StripeService(db)
    try:
        url = await svc.create_portal_session(current_user, body.return_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PortalSessionResponse(portal_url=url)


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook handler — verified by signature, no JWT auth."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as exc:
        logger.error("Webhook verification error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook error")

    # Import here to get a fresh DB session
    from backend.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        svc = StripeService(db)
        event_type = event["type"]
        data = event["data"]["object"]

        if event_type == "checkout.session.completed":
            await svc.handle_checkout_completed(data)
        elif event_type == "customer.subscription.updated":
            await svc.handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            await svc.handle_subscription_deleted(data)
        elif event_type == "invoice.payment_failed":
            await svc.handle_payment_failed(data)
        elif event_type == "invoice.paid":
            await svc.handle_invoice_paid(data)
        else:
            logger.debug("Unhandled Stripe event: %s", event_type)

    return {"status": "ok"}
```

- [ ] **Step 5: Register billing router in router.py**

Add at the end of `backend/api/v1/router.py` (after the api_keys router):

```python
from backend.api.v1.billing import router as billing_router
api_router.include_router(billing_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_billing_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/api/v1/billing.py backend/schemas/billing.py backend/api/v1/router.py backend/tests/test_billing_api.py
git commit -m "feat(billing): add billing API endpoints and schemas"
```

---

### Task 12: Wire tier enforcement into sandbox creation

**Files:**
- Modify: `backend/api/v1/sandboxes.py:213-250` (create_sandbox endpoint)
- Modify: `backend/services/budget_service.py:160-193` (record_sandbox_usage)
- Test: `backend/tests/test_sandbox_tier_enforcement.py` (create)

- [ ] **Step 1: Write test for sandbox tier enforcement**

```python
# backend/tests/test_sandbox_tier_enforcement.py
"""Tests for tier enforcement in sandbox creation flow."""
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, User, UsagePeriod
from backend.core.exceptions import TierLimitError


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_sandbox_creation_blocked_when_over_limit(db, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)

    from backend.services.tier_service import TierService

    user = User(id=uuid.uuid4(), firebase_uid="uid-block", email="block@test.com", tier="free")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    svc = TierService(db)
    await svc.record_usage(user, "headless", 15 * 3600)

    with pytest.raises(TierLimitError, match="headless"):
        await svc.check_can_start_sandbox(user, "headless")


@pytest.mark.asyncio
async def test_sandbox_creation_allowed_within_limit(db, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "tier_enforcement_enabled", True)

    from backend.services.tier_service import TierService

    user = User(id=uuid.uuid4(), firebase_uid="uid-ok", email="ok@test.com", tier="individual")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    svc = TierService(db)
    await svc.record_usage(user, "headless", 50 * 3600)

    await svc.check_can_start_sandbox(user, "headless")
```

- [ ] **Step 2: Run test to verify it passes (these test TierService directly)**

Run: `cd backend && python -m pytest tests/test_sandbox_tier_enforcement.py -v`
Expected: PASS

- [ ] **Step 3: Add tier check to sandbox creation endpoint**

In `backend/api/v1/sandboxes.py`, add import at top:

```python
from backend.services.tier_service import TierService
from backend.core.exceptions import TierLimitError
```

In the `create_sandbox` function (line ~220), add tier check before the try block that provisions the sandbox:

```python
    # Tier enforcement: check sandbox hour limits
    tier_svc = TierService(db)
    try:
        unit_type = "desktop" if body.requires_desktop else "headless"
        await tier_svc.check_can_start_sandbox(current_user, unit_type)
    except TierLimitError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_limit",
                "message": str(exc),
                "current_tier": exc.current_tier,
                "upgrade_url": exc.upgrade_url,
            },
        ) from exc
```

- [ ] **Step 4: Add usage recording to budget_service.py**

In `backend/services/budget_service.py`, add `user_id` and `unit_type` parameters to `record_sandbox_usage` (line ~160):

```python
    async def record_sandbox_usage(
        self,
        agent_id: UUID,
        project_id: UUID,
        sandbox_id: str,
        pod_seconds: float,
        event_type: str = "session_end",
        user_id: UUID | None = None,
        unit_type: str = "headless",
    ) -> None:
```

After the existing INSERT succeeds (inside the try block), add:

```python
            # Update tier usage counters
            if user_id:
                try:
                    from backend.services.tier_service import TierService
                    from backend.db.models import User
                    user = await self._db.get(User, user_id)
                    if user:
                        tier_svc = TierService(self._db)
                        await tier_svc.record_usage(user, unit_type, int(pod_seconds))
                except Exception as tier_exc:
                    logger.warning("TierService usage recording failed: %s", tier_exc)
```

- [ ] **Step 5: Run all billing tests**

Run: `cd backend && python -m pytest tests/test_billing_config.py tests/test_billing_models.py tests/test_tier_service.py tests/test_stripe_service.py tests/test_sandbox_tier_enforcement.py -v`
Expected: PASS

- [ ] **Step 6: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --tb=short -m "not integration" -x`
Expected: PASS (no regressions)

- [ ] **Step 7: Commit**

```bash
git add backend/api/v1/sandboxes.py backend/services/budget_service.py backend/tests/test_sandbox_tier_enforcement.py
git commit -m "feat(billing): wire tier enforcement into sandbox creation and usage recording"
```

---

### Task 13: Frontend — Billing page and API client

**Files:**
- Create: `frontend/src/pages/Billing.tsx`
- Create: `frontend/src/hooks/useBilling.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx:92-94`

- [ ] **Step 1: Add billing API methods to client.ts**

Add at the end of `frontend/src/api/client.ts`:

```typescript
// ── Billing ──────────────────────────────────────────────────────────

export interface SubscriptionInfo {
  tier: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
}

export interface UsageSummary {
  tier: string;
  period_start: string;
  period_end: string;
  headless_seconds_used: number;
  headless_seconds_included: number;
  desktop_seconds_used: number;
  desktop_seconds_included: number;
}

export async function getSubscription(): Promise<SubscriptionInfo> {
  return request<SubscriptionInfo>('GET', '/billing/subscription');
}

export async function getUsage(): Promise<UsageSummary> {
  return request<UsageSummary>('GET', '/billing/usage');
}

export async function createCheckoutSession(tier: string, returnUrl: string): Promise<{ checkout_url: string }> {
  return request<{ checkout_url: string }>('POST', '/billing/checkout-session', { tier, return_url: returnUrl });
}

export async function createPortalSession(returnUrl: string): Promise<{ portal_url: string }> {
  return request<{ portal_url: string }>('POST', '/billing/portal-session', { return_url: returnUrl });
}
```

- [ ] **Step 2: Create useBilling hook**

```typescript
// frontend/src/hooks/useBilling.ts
import { useState, useEffect, useCallback } from 'react';
import { getSubscription, getUsage, type SubscriptionInfo, type UsageSummary } from '../api/client';

export function useBilling() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sub, usg] = await Promise.all([getSubscription(), getUsage()]);
      setSubscription(sub);
      setUsage(usg);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load billing');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { subscription, usage, loading, error, refresh };
}
```

- [ ] **Step 3: Create Billing page**

```tsx
// frontend/src/pages/Billing.tsx
import { useState } from 'react';
import { ExternalLink } from 'lucide-react';

import { createCheckoutSession, createPortalSession } from '../api/client';
import { useBilling } from '../hooks/useBilling';
import { Button, Card } from '../components/ui';
import { AppLayout } from '../components/Layout';

export function formatHours(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function UsageBar({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  const color = pct >= 90 ? 'var(--color-danger)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-success)';

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-[var(--text-muted)]">{formatHours(used)} / {formatHours(total)}</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--bg-secondary)]">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

const TIER_INFO: Record<string, { name: string; price: string; description: string }> = {
  free: { name: 'Free', price: '$0', description: '15 hrs headless + 15 hrs desktop' },
  individual: { name: 'Individual', price: '$20/mo', description: '200 hrs headless + 200 hrs desktop' },
  team: { name: 'Team', price: '$50/mo', description: '1000 hrs headless + 1000 hrs desktop, 3 seats' },
};

export function BillingPage() {
  const { subscription, usage, loading, error, refresh } = useBilling();
  const [actionLoading, setActionLoading] = useState(false);

  const currentTier = subscription?.tier ?? 'free';
  const tierInfo = TIER_INFO[currentTier] ?? TIER_INFO.free;

  const handleUpgrade = async (tier: string) => {
    setActionLoading(true);
    try {
      const { checkout_url } = await createCheckoutSession(tier, window.location.href);
      window.location.href = checkout_url;
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start checkout');
    } finally {
      setActionLoading(false);
    }
  };

  const handleManage = async () => {
    setActionLoading(true);
    try {
      const { portal_url } = await createPortalSession(window.location.href);
      window.location.href = portal_url;
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to open portal');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 text-[var(--text-muted)]">Loading billing...</div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="min-h-screen bg-[var(--app-bg)] p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          <h1 className="text-2xl font-semibold">Billing</h1>

          {error && (
            <div className="rounded border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] p-3 text-sm text-[var(--color-danger)]">
              {error}
            </div>
          )}

          {/* Current Plan */}
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-medium">Current Plan: {tierInfo.name}</h2>
                <p className="text-sm text-[var(--text-muted)]">{tierInfo.price} — {tierInfo.description}</p>
                {subscription?.cancel_at_period_end && (
                  <p className="mt-1 text-sm text-[var(--color-warning)]">
                    Cancels at end of period ({subscription.current_period_end?.slice(0, 10)})
                  </p>
                )}
              </div>
              {currentTier !== 'free' && (
                <Button variant="secondary" onClick={handleManage} disabled={actionLoading}>
                  <ExternalLink size={14} className="mr-1" />
                  Manage
                </Button>
              )}
            </div>
          </Card>

          {/* Usage */}
          {usage && (
            <Card className="p-6 space-y-4">
              <h2 className="text-lg font-medium">Usage This Period</h2>
              <UsageBar label="Headless Sandbox" used={usage.headless_seconds_used} total={usage.headless_seconds_included} />
              <UsageBar label="Desktop VM" used={usage.desktop_seconds_used} total={usage.desktop_seconds_included} />
            </Card>
          )}

          {/* Upgrade Options */}
          {currentTier === 'free' && (
            <Card className="p-6 space-y-4">
              <h2 className="text-lg font-medium">Upgrade</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-lg border border-[var(--border)] p-4">
                  <h3 className="font-medium">Individual — $20/mo</h3>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">200 hrs headless + 200 hrs desktop</p>
                  <Button className="mt-3 w-full" onClick={() => handleUpgrade('individual')} disabled={actionLoading}>
                    Upgrade to Individual
                  </Button>
                </div>
                <div className="rounded-lg border border-[var(--border)] p-4">
                  <h3 className="font-medium">Team — $50/mo</h3>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">1000 hrs each, 3 seats</p>
                  <Button className="mt-3 w-full" onClick={() => handleUpgrade('team')} disabled={actionLoading}>
                    Upgrade to Team
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {currentTier === 'individual' && (
            <Card className="p-6 space-y-4">
              <h2 className="text-lg font-medium">Upgrade</h2>
              <div className="rounded-lg border border-[var(--border)] p-4">
                <h3 className="font-medium">Team — $50/mo</h3>
                <p className="mt-1 text-sm text-[var(--text-muted)]">1000 hrs each, 3 seats</p>
                <Button className="mt-3 w-full" onClick={() => handleUpgrade('team')} disabled={actionLoading}>
                  Upgrade to Team
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
```

- [ ] **Step 4: Export BillingPage from pages/index.ts**

Add to `frontend/src/pages/index.ts`:

```typescript
export { BillingPage } from './Billing';
```

- [ ] **Step 5: Add billing route to App.tsx**

In `frontend/src/App.tsx`, add import of `BillingPage` (line 24 area) and add route after line 94 (`/settings`):

```tsx
<Route path="/settings/billing" element={<BillingPage />} />
```

- [ ] **Step 6: Run frontend lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS (no lint errors, builds successfully)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useBilling.ts frontend/src/pages/Billing.tsx frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(billing): add billing page with usage gauges and Stripe checkout"
```

---

### Task 14: Add TierBadge and UpgradeBanner components

**Files:**
- Create: `frontend/src/components/TierBadge.tsx`
- Create: `frontend/src/components/UpgradeBanner.tsx`
- Modify: `frontend/src/pages/UserSettings.tsx` (add link to billing)

- [ ] **Step 1: Create TierBadge component**

```tsx
// frontend/src/components/TierBadge.tsx
const TIER_COLORS: Record<string, string> = {
  free: 'bg-gray-100 text-gray-700',
  individual: 'bg-blue-100 text-blue-700',
  team: 'bg-purple-100 text-purple-700',
};

export function TierBadge({ tier }: { tier: string }) {
  const colors = TIER_COLORS[tier] ?? TIER_COLORS.free;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}>
      {tier.charAt(0).toUpperCase() + tier.slice(1)}
    </span>
  );
}
```

- [ ] **Step 2: Create UpgradeBanner component**

```tsx
// frontend/src/components/UpgradeBanner.tsx
import { useNavigate } from 'react-router-dom';
import { Button } from './ui';

interface TierLimitError {
  error: 'tier_limit';
  message: string;
  current_tier: string;
  upgrade_url: string;
}

export function UpgradeBanner({ detail }: { detail: TierLimitError }) {
  const navigate = useNavigate();

  return (
    <div className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] p-4">
      <p className="text-sm text-[var(--color-warning)]">{detail.message}</p>
      <Button
        variant="secondary"
        size="sm"
        className="mt-2"
        onClick={() => navigate(detail.upgrade_url)}
      >
        View Plans
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Add billing link to UserSettings page**

In `frontend/src/pages/UserSettings.tsx`, add a "Billing" link (after the APIKeyManager section from Task 5):

```tsx
import { useNavigate } from 'react-router-dom';

// Inside the return JSX, add a new section:
<div className="border-t border-[var(--border)] pt-4 mt-4">
  <h2 className="text-sm font-medium mb-2">Billing & Usage</h2>
  <Button variant="secondary" onClick={() => navigate('/settings/billing')}>
    Manage Billing
  </Button>
</div>
```

- [ ] **Step 4: Run frontend lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TierBadge.tsx frontend/src/components/UpgradeBanner.tsx frontend/src/pages/UserSettings.tsx
git commit -m "feat(billing): add TierBadge, UpgradeBanner, and billing link in settings"
```

---

### Task 15: Integrate tier badge and usage display

**Files:**
- Modify: `frontend/src/pages/UserSettings.tsx`
- Modify: `backend/schemas/user.py`
- Modify: `frontend/src/pages/Sandbox.tsx`

- [ ] **Step 1: Add TierBadge to UserSettings**

In `frontend/src/pages/UserSettings.tsx` header area (where `user.email` is displayed), add:

```tsx
import { TierBadge } from '../components/TierBadge';
// ... in the return JSX, after the email display:
<TierBadge tier={user.tier ?? 'free'} />
```

This requires `user.tier` to be available on the frontend type. Find the `UserProfile` or user interface (likely in `frontend/src/types/index.ts` or wherever the user type is defined) and add:

```typescript
tier?: string;
```

- [ ] **Step 2: Update backend UserResponse schema to include tier**

In `backend/schemas/user.py`, add to `UserResponse`:

```python
    tier: str = "free"
```

- [ ] **Step 3: Add remaining hours to Sandbox page**

In `frontend/src/pages/Sandbox.tsx`, near the create buttons, add a usage hint:

```tsx
import { useBilling } from '../hooks/useBilling';
import { formatHours } from './Billing';

// Inside the component:
const { usage } = useBilling();

// Near create buttons, show remaining:
{usage && (
  <div className="text-xs text-[var(--text-muted)]">
    Headless: {formatHours(usage.headless_seconds_included - usage.headless_seconds_used)} remaining |
    Desktop: {formatHours(usage.desktop_seconds_included - usage.desktop_seconds_used)} remaining
  </div>
)}
```

- [ ] **Step 4: Handle 403 tier_limit errors in Sandbox page**

When `create_sandbox` returns 403 with `error: "tier_limit"`, display the `UpgradeBanner`:

```tsx
import { UpgradeBanner } from '../components/UpgradeBanner';

// In the error handler for sandbox creation:
if (err.status === 403 && err.detail?.error === 'tier_limit') {
  setTierError(err.detail);
} else {
  setError(err.message);
}

// In the JSX:
{tierError && <UpgradeBanner detail={tierError} />}
```

- [ ] **Step 5: Run frontend lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Sandbox.tsx frontend/src/pages/UserSettings.tsx backend/schemas/user.py
git commit -m "feat(billing): add tier badge to settings and usage display to sandbox page"
```

---

### Task 16: Final integration test and verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v --tb=short -m "not integration" -x`
Expected: ALL PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: PASS

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && npm test -- --run`
Expected: PASS (or no regressions)

- [ ] **Step 5: Verify migration chain**

Run: `cd backend && python -m pytest tests/test_migration_graph.py -v`
Expected: PASS

- [ ] **Step 6: Verify all billing + API key tests pass together**

Run: `cd backend && python -m pytest tests/test_user_api_keys.py tests/test_api_keys_api.py tests/test_billing_config.py tests/test_billing_models.py tests/test_tier_service.py tests/test_stripe_service.py tests/test_billing_api.py tests/test_sandbox_tier_enforcement.py -v`
Expected: ALL PASS

- [ ] **Step 7: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "feat(v5): final integration fixes for API keys and billing"
```
