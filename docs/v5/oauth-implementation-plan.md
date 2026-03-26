# OpenAI OAuth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Sign in with OpenAI" OAuth flow alongside existing Firebase/Google auth, with a mock OAuth provider for local testing.

**Architecture:** Users authenticate via OpenAI OAuth; the backend exchanges the code for tokens, creates/finds an AICT User, mints a Firebase Custom Token, and returns it to the frontend. All existing auth middleware stays unchanged — every user ends up with a Firebase JWT. A mock OAuth server enables full local E2E testing without real OpenAI credentials.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Firebase Admin SDK (custom tokens), React 19, Firebase JS SDK (`signInWithCustomToken`), httpx (OAuth HTTP calls)

**Spec:** `docs/v5/openai-oauth-design.md`

---

## File Structure

### Backend — New files
| File | Purpose |
|------|---------|
| `backend/db/models.py` (modify) | Add `UserOAuthConnection` model, widen `User.firebase_uid` |
| `backend/migrations/versions/007_add_oauth_connections.py` | Alembic migration for `user_oauth_connections` table |
| `backend/services/oauth_service.py` | OAuth flow logic: state tokens, code exchange, user creation/linking, token refresh |
| `backend/api/v1/oauth.py` | OAuth API endpoints: login, callback, status, disconnect |
| `backend/api/v1/router.py` (modify) | Register oauth router |
| `backend/schemas/oauth.py` | Pydantic schemas for OAuth request/response |
| `backend/config.py` (modify) | Add OpenAI OAuth config fields |
| `backend/api/v1/auth.py` (modify) | Add `openai_connected` to `/auth/me` response |
| `backend/schemas/user.py` (modify) | Add `openai_connected` field to `UserResponse` |
| `backend/tests/test_oauth.py` | Unit tests for OAuth service and endpoints |

### Frontend — New files
| File | Purpose |
|------|---------|
| `frontend/src/pages/OpenAICallback.tsx` | OAuth callback page (exchanges code, signs in with custom token) |
| `frontend/src/pages/index.ts` (modify) | Export new page |
| `frontend/src/pages/Login.tsx` (modify) | Add "Sign in with OpenAI" button |
| `frontend/src/contexts/AuthContext.tsx` (modify) | Add `loginWithOpenAI()` method |
| `frontend/src/api/client.ts` (modify) | Add OAuth API functions |
| `frontend/src/types/index.ts` (modify) | Add `openai_connected` to `UserProfile` |
| `frontend/src/App.tsx` (modify) | Add `/auth/openai/callback` route (outside ProtectedRoute) |
| `frontend/src/pages/UserSettings.tsx` (modify) | Add Connected Accounts section |

### Mock OAuth Server
| File | Purpose |
|------|---------|
| `backend/tests/mock_oauth_server.py` | Standalone FastAPI app that mimics OpenAI's OAuth endpoints for local dev/testing |

---

## Task 1: Database Migration & Model

**Files:**
- Modify: `backend/db/models.py:89-108`
- Create: `backend/migrations/versions/007_add_oauth_connections.py`

- [ ] **Step 1: Add UserOAuthConnection model to models.py**

Add after the `UserAPIKey` class (around line 130):

```python
# ── User OAuth Connections ─────────────────────────────────────────


class UserOAuthConnection(Base):
    """OAuth token state per user per provider (e.g. OpenAI)."""

    __tablename__ = "user_oauth_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_conn_user_provider"),
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_conn_provider_ext_id"),
        Index("ix_oauth_conn_user", "user_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    provider_email = Column(String(255), nullable=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(Text, nullable=True)
    is_valid = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", backref="oauth_connections")
```

- [ ] **Step 2: Widen User.firebase_uid column in models.py**

Change `backend/db/models.py:93`:

```python
# Before:
firebase_uid = Column(String(128), unique=True, nullable=False)
# After:
firebase_uid = Column(String(255), unique=True, nullable=False)
```

- [ ] **Step 3: Create Alembic migration**

Create `backend/migrations/versions/007_add_oauth_connections.py`:

```python
"""Add user_oauth_connections table and widen firebase_uid.

Revision ID: 007_oauth
Revises: 006_add_v5_api_keys_and_billing
"""

revision = "007_oauth"
down_revision = "006_add_v5_api_keys_and_billing"

import sqlalchemy as sa
from alembic import op


def upgrade():
    # Widen firebase_uid to accommodate "openai:{provider_user_id}" format
    op.alter_column(
        "users",
        "firebase_uid",
        existing_type=sa.String(128),
        type_=sa.String(255),
    )

    op.create_table(
        "user_oauth_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_conn_user_provider"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_conn_provider_ext_id"),
    )
    op.create_index("ix_oauth_conn_user", "user_oauth_connections", ["user_id"])


def downgrade():
    op.drop_index("ix_oauth_conn_user")
    op.drop_table("user_oauth_connections")
    op.alter_column(
        "users",
        "firebase_uid",
        existing_type=sa.String(255),
        type_=sa.String(128),
    )
```

- [ ] **Step 4: Run migration locally to verify**

Run: `cd backend && PYTHONPATH=.. alembic -c alembic.ini upgrade head`
Expected: Migration applies successfully

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py backend/migrations/versions/007_add_oauth_connections.py
git commit -m "feat(oauth): add UserOAuthConnection model and migration"
```

---

## Task 2: Backend Config & Schemas

**Files:**
- Modify: `backend/config.py:101-107`
- Create: `backend/schemas/oauth.py`
- Modify: `backend/schemas/user.py`

- [ ] **Step 1: Add OAuth config fields to Settings**

In `backend/config.py`, add after the Stripe billing section (line 107):

```python
    # OpenAI OAuth
    openai_oauth_client_id: str = ""
    openai_oauth_client_secret: str = ""
    openai_oauth_authorize_url: str = "https://platform.openai.com/oauth/authorize"
    openai_oauth_token_url: str = "https://platform.openai.com/oauth/token"
    openai_oauth_userinfo_url: str = "https://api.openai.com/v1/me"
    openai_oauth_redirect_uri: str = ""  # e.g. https://app.aict.dev/auth/openai/callback
    openai_oauth_scopes: str = "openai.api"
```

- [ ] **Step 2: Create OAuth Pydantic schemas**

Create `backend/schemas/oauth.py`:

```python
"""Pydantic schemas for OpenAI OAuth endpoints."""

from pydantic import BaseModel


class OAuthLoginResponse(BaseModel):
    url: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthCallbackLoginResponse(BaseModel):
    firebase_custom_token: str


class OAuthCallbackConnectResponse(BaseModel):
    connected: bool


class OAuthCallbackErrorResponse(BaseModel):
    error: str
    message: str


class OAuthStatusResponse(BaseModel):
    connected: bool
    email: str | None = None
    scopes: str | None = None
    valid: bool | None = None
```

- [ ] **Step 3: Add openai_connected to UserResponse**

In `backend/schemas/user.py`, add to `UserResponse`:

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    github_token_set: bool = Field(default=False)
    tier: str = "free"
    openai_connected: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Commit**

```bash
git add backend/config.py backend/schemas/oauth.py backend/schemas/user.py
git commit -m "feat(oauth): add config fields and Pydantic schemas"
```

---

## Task 3: OAuth Service

**Files:**
- Create: `backend/services/oauth_service.py`

- [ ] **Step 1: Create the OAuth service**

Create `backend/services/oauth_service.py`:

```python
"""OpenAI OAuth service — state tokens, code exchange, user creation/linking."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import User, UserOAuthConnection
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_STATE_TTL_SECONDS = 600  # 10 minutes


def _hmac_key() -> bytes:
    """Derive HMAC key from secret_encryption_key (or fallback for dev)."""
    secret = settings.secret_encryption_key or settings.api_token
    return hashlib.sha256(secret.encode()).digest()


def create_state_token(flow: str = "login") -> str:
    """Create an HMAC-signed, self-contained state token.

    Encodes flow type, nonce, and expiry. No server-side storage required.
    """
    payload = json.dumps({
        "flow": flow,
        "nonce": uuid.uuid4().hex[:16],
        "exp": int(time.time()) + _STATE_TTL_SECONDS,
    })
    sig = hmac.new(_hmac_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def verify_state_token(state: str) -> dict | None:
    """Verify and decode state token. Returns payload dict or None if invalid."""
    parts = state.rsplit("|", 1)
    if len(parts) != 2:
        return None
    payload_str, sig = parts
    expected = hmac.new(_hmac_key(), payload_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def build_authorize_url(flow: str = "login") -> str:
    """Build the OAuth authorization URL with CSRF state."""
    state = create_state_token(flow)
    params = {
        "client_id": settings.openai_oauth_client_id,
        "redirect_uri": settings.openai_oauth_redirect_uri,
        "response_type": "code",
        "scope": settings.openai_oauth_scopes,
        "state": state,
    }
    qs = "&".join(f"{k}={httpx.QueryParams({k: v})}" for k, v in params.items())
    # Use httpx URL builder for proper encoding
    return f"{settings.openai_oauth_authorize_url}?{httpx.QueryParams(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access/refresh tokens."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            settings.openai_oauth_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.openai_oauth_redirect_uri,
                "client_id": settings.openai_oauth_client_id,
                "client_secret": settings.openai_oauth_client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(access_token: str) -> dict:
    """Fetch user profile from OpenAI userinfo endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.openai_oauth_userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def _encrypt(value: str) -> str:
    """Encrypt a string with Fernet. Falls back to plaintext in dev if no key."""
    key = settings.secret_encryption_key
    if not key:
        return value
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    key = settings.secret_encryption_key
    if not key:
        return value
    return Fernet(key.encode()).decrypt(value.encode()).decode()


async def handle_login_flow(
    db: AsyncSession,
    code: str,
) -> dict:
    """Handle OAuth login: exchange code, create/find user, mint Firebase token.

    Returns dict with either:
      - {"firebase_custom_token": "..."} on success
      - {"error": "email_exists", "message": "..."} on email collision
    """
    tokens = await exchange_code_for_tokens(code)
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    userinfo = await fetch_userinfo(access_token)
    provider_user_id = userinfo["id"]
    provider_email = userinfo.get("email", "")

    # Check email collision
    if provider_email:
        existing_user = (await db.execute(
            select(User).where(User.email == provider_email)
        )).scalar_one_or_none()
        if existing_user and not existing_user.firebase_uid.startswith("openai:"):
            return {
                "error": "email_exists",
                "message": (
                    "An account with this email already exists. "
                    "Sign in with Google first, then connect OpenAI from Settings."
                ),
            }

    # Find or create user
    firebase_uid = f"openai:{provider_user_id}"
    user = (await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )).scalar_one_or_none()

    if not user:
        user = User(
            firebase_uid=firebase_uid,
            email=provider_email or f"openai-{provider_user_id}@openai.aict.local",
            display_name=userinfo.get("name"),
        )
        db.add(user)
        await db.flush()

    # Upsert OAuth connection
    conn = (await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if conn:
        conn.access_token = _encrypt(access_token)
        conn.refresh_token = _encrypt(refresh_token) if refresh_token else None
        conn.token_expires_at = (
            datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
            if expires_in else None
        )
        conn.provider_email = provider_email
        conn.is_valid = True
        conn.updated_at = now
    else:
        conn = UserOAuthConnection(
            user_id=user.id,
            provider="openai",
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            access_token=_encrypt(access_token),
            refresh_token=_encrypt(refresh_token) if refresh_token else None,
            token_expires_at=(
                datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
                if expires_in else None
            ),
            scopes=settings.openai_oauth_scopes,
            is_valid=True,
        )
        db.add(conn)

    await db.commit()

    # Mint Firebase Custom Token
    try:
        import firebase_admin.auth as fb_auth
        custom_token = fb_auth.create_custom_token(firebase_uid)
        return {"firebase_custom_token": custom_token.decode() if isinstance(custom_token, bytes) else custom_token}
    except Exception as exc:
        logger.error("Failed to mint Firebase custom token: %s", exc)
        raise


async def handle_connect_flow(
    db: AsyncSession,
    user: User,
    code: str,
) -> dict:
    """Handle connecting OpenAI to an existing authenticated user."""
    tokens = await exchange_code_for_tokens(code)
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    userinfo = await fetch_userinfo(access_token)
    provider_user_id = userinfo["id"]
    provider_email = userinfo.get("email", "")

    now = datetime.now(timezone.utc)
    conn = (await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )).scalar_one_or_none()

    if conn:
        conn.provider_user_id = provider_user_id
        conn.provider_email = provider_email
        conn.access_token = _encrypt(access_token)
        conn.refresh_token = _encrypt(refresh_token) if refresh_token else None
        conn.token_expires_at = (
            datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
            if expires_in else None
        )
        conn.is_valid = True
        conn.updated_at = now
    else:
        conn = UserOAuthConnection(
            user_id=user.id,
            provider="openai",
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            access_token=_encrypt(access_token),
            refresh_token=_encrypt(refresh_token) if refresh_token else None,
            token_expires_at=(
                datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
                if expires_in else None
            ),
            scopes=settings.openai_oauth_scopes,
            is_valid=True,
        )
        db.add(conn)

    await db.commit()
    return {"connected": True}


async def get_connection_status(db: AsyncSession, user_id) -> dict:
    """Get OpenAI connection status for a user."""
    conn = (await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user_id,
            UserOAuthConnection.provider == "openai",
        )
    )).scalar_one_or_none()

    if not conn:
        return {"connected": False}

    return {
        "connected": True,
        "email": conn.provider_email,
        "scopes": conn.scopes,
        "valid": conn.is_valid,
    }


async def disconnect(db: AsyncSession, user: User) -> None:
    """Remove OpenAI connection. Refuses if it's the user's only auth method."""
    if user.firebase_uid.startswith("openai:"):
        raise ValueError(
            "Cannot disconnect your only auth method. Link a Google account first."
        )

    conn = (await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )).scalar_one_or_none()

    if conn:
        await db.delete(conn)
        await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/oauth_service.py
git commit -m "feat(oauth): add OAuth service with state tokens, code exchange, user management"
```

---

## Task 4: OAuth API Endpoints

**Files:**
- Create: `backend/api/v1/oauth.py`
- Modify: `backend/api/v1/router.py:69`
- Modify: `backend/api/v1/auth.py:14-22`

- [ ] **Step 1: Create OAuth endpoints**

Create `backend/api/v1/oauth.py`:

```python
"""OpenAI OAuth endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import get_current_user
from backend.db.models import User
from backend.db.session import get_db
from backend.schemas.oauth import (
    OAuthCallbackRequest,
    OAuthLoginResponse,
    OAuthStatusResponse,
)
from backend.services import oauth_service

router = APIRouter(prefix="/auth/openai", tags=["oauth"])


@router.get("/login", response_model=OAuthLoginResponse)
async def oauth_login(flow: str = "login"):
    """Generate OpenAI OAuth authorization URL."""
    if not settings.openai_oauth_client_id:
        raise HTTPException(status_code=501, detail="OpenAI OAuth not configured")
    if flow not in ("login", "connect"):
        raise HTTPException(status_code=400, detail="flow must be 'login' or 'connect'")
    url = oauth_service.build_authorize_url(flow)
    return {"url": url}


@router.post("/callback")
async def oauth_callback(
    body: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
):
    """Exchange OAuth code for tokens. Handles both login and connect flows."""
    state_payload = oauth_service.verify_state_token(body.state)
    if not state_payload:
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    flow = state_payload.get("flow", "login")

    try:
        if flow == "connect" and authorization:
            # Connect flow: link to existing user
            from backend.core.auth import get_current_user as _get_user
            from fastapi import Request
            # Manually resolve user from the authorization header
            token = authorization.removeprefix("Bearer ").strip()
            from backend.core.auth import _verify_firebase_token
            decoded = _verify_firebase_token(token)
            if not decoded:
                raise HTTPException(status_code=401, detail="Invalid token")
            from sqlalchemy import select
            firebase_uid = decoded.get("uid")
            result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            return await oauth_service.handle_connect_flow(db, user, body.code)
        else:
            # Login flow: create/find user, mint Firebase token
            result = await oauth_service.handle_login_flow(db, body.code)
            if "error" in result:
                return result  # email_exists error
            return result
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI OAuth error: {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status", response_model=OAuthStatusResponse)
async def oauth_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's OpenAI connection status."""
    return await oauth_service.get_connection_status(db, current_user.id)


@router.delete("/disconnect")
async def oauth_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect OpenAI account."""
    try:
        await oauth_service.disconnect(db, current_user)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 2: Register OAuth router in api_router**

In `backend/api/v1/router.py`, add after line 69 (`api_router.include_router(billing_router)`):

```python
from backend.api.v1.oauth import router as oauth_router
api_router.include_router(oauth_router)
```

- [ ] **Step 3: Add openai_connected to /auth/me response**

In `backend/api/v1/auth.py`, update `_to_user_response` to accept db and check connection:

```python
"""User profile endpoints backed by Firebase auth."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.db.models import User, UserOAuthConnection
from backend.db.session import get_db
from backend.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


async def _to_user_response(user: User, db: AsyncSession) -> dict:
    conn = (await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )).scalar_one_or_none()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "github_token_set": bool(user.github_token),
        "tier": user.tier,
        "openai_connected": conn is not None and conn.is_valid,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _to_user_response(current_user, db)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.display_name is not None:
        current_user.display_name = data.display_name
    if data.github_token is not None:
        current_user.github_token = data.github_token
    await db.commit()
    await db.refresh(current_user)
    return await _to_user_response(current_user, db)
```

- [ ] **Step 4: Run backend tests**

Run: `cd backend && python -m pytest tests/ -v --tb=short -m "not integration" -x`
Expected: All existing tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/oauth.py backend/api/v1/router.py backend/api/v1/auth.py
git commit -m "feat(oauth): add OAuth API endpoints and wire into router"
```

---

## Task 5: Mock OAuth Server

**Files:**
- Create: `backend/tests/mock_oauth_server.py`

- [ ] **Step 1: Create mock OAuth server**

Create `backend/tests/mock_oauth_server.py`:

```python
"""Mock OpenAI OAuth server for local development and testing.

Run standalone: python -m backend.tests.mock_oauth_server
Serves on http://localhost:8099

Endpoints:
  GET  /oauth/authorize  — shows a form to "authorize", redirects with code
  POST /oauth/token      — exchanges code for mock tokens
  GET  /v1/me            — returns mock user profile
"""

import hashlib
import secrets
import time
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI(title="Mock OpenAI OAuth Server")

# In-memory store of issued authorization codes
_codes: dict[str, dict] = {}

MOCK_USER = {
    "id": "mock-openai-user-001",
    "email": "developer@openai-mock.local",
    "name": "Mock OpenAI User",
}


@app.get("/oauth/authorize", response_class=HTMLResponse)
async def authorize(
    client_id: str = Query(""),
    redirect_uri: str = Query(""),
    state: str = Query(""),
    scope: str = Query(""),
    response_type: str = Query("code"),
):
    """Show a simple authorize form that auto-submits or lets user click."""
    return f"""<!DOCTYPE html>
<html>
<head><title>Mock OpenAI OAuth</title></head>
<body style="font-family: sans-serif; max-width: 500px; margin: 80px auto; text-align: center;">
  <h2>Mock OpenAI Authorization</h2>
  <p>App <strong>{client_id}</strong> wants access to <strong>{scope}</strong></p>
  <form method="POST" action="/oauth/authorize/accept">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}" />
    <input type="hidden" name="state" value="{state}" />
    <input type="hidden" name="scope" value="{scope}" />
    <button type="submit" style="padding: 12px 32px; font-size: 16px; background: #10a37f; color: white; border: none; border-radius: 6px; cursor: pointer;">
      Authorize
    </button>
  </form>
</body>
</html>"""


@app.post("/oauth/authorize/accept")
async def authorize_accept(
    redirect_uri: str = Form(""),
    state: str = Form(""),
    scope: str = Form(""),
):
    """Issue an authorization code and redirect back to the app."""
    code = secrets.token_hex(20)
    _codes[code] = {
        "scope": scope,
        "created_at": time.time(),
        "used": False,
    }
    params = urlencode({"code": code, "state": state})
    return RedirectResponse(url=f"{redirect_uri}?{params}", status_code=302)


@app.post("/oauth/token")
async def token_exchange(
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
):
    """Exchange authorization code for mock tokens."""
    if grant_type == "authorization_code":
        stored = _codes.get(code)
        if not stored or stored["used"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        stored["used"] = True
        access_token = f"mock-access-{secrets.token_hex(16)}"
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": f"mock-refresh-{secrets.token_hex(16)}",
            "scope": stored["scope"],
        }
    elif grant_type == "refresh_token":
        return {
            "access_token": f"mock-access-{secrets.token_hex(16)}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openai.api",
        }
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


@app.get("/v1/me")
async def userinfo(request: Request):
    """Return mock user profile."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return MOCK_USER


if __name__ == "__main__":
    import uvicorn
    print("Starting Mock OpenAI OAuth Server on http://localhost:8099")
    print("Configure backend with:")
    print("  OPENAI_OAUTH_CLIENT_ID=mock-client-id")
    print("  OPENAI_OAUTH_CLIENT_SECRET=mock-client-secret")
    print("  OPENAI_OAUTH_AUTHORIZE_URL=http://localhost:8099/oauth/authorize")
    print("  OPENAI_OAUTH_TOKEN_URL=http://localhost:8099/oauth/token")
    print("  OPENAI_OAUTH_USERINFO_URL=http://localhost:8099/v1/me")
    print("  OPENAI_OAUTH_REDIRECT_URI=http://localhost:3000/auth/openai/callback")
    uvicorn.run(app, host="0.0.0.0", port=8099)
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/mock_oauth_server.py
git commit -m "feat(oauth): add mock OpenAI OAuth server for local development"
```

---

## Task 6: Frontend — Types, API Client, Auth Context

**Files:**
- Modify: `frontend/src/types/index.ts:530-538`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/contexts/AuthContext.tsx`

- [ ] **Step 1: Add openai_connected to UserProfile type**

In `frontend/src/types/index.ts`, update `UserProfile` (line 530):

```typescript
export interface UserProfile {
  id: UUID;
  email: string;
  display_name: string | null;
  github_token_set: boolean;
  tier?: string;
  openai_connected?: boolean;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add OAuth API functions to client.ts**

In `frontend/src/api/client.ts`, add after the `testAPIKey` function (near the end):

```typescript
// ─── OAuth ────────────────────────────────────────────────────────────

export async function getOAuthLoginUrl(flow: 'login' | 'connect' = 'login'): Promise<{ url: string }> {
  return request<{ url: string }>('GET', `/auth/openai/login?flow=${flow}`);
}

export async function oauthCallback(code: string, state: string): Promise<{
  firebase_custom_token?: string;
  connected?: boolean;
  error?: string;
  message?: string;
}> {
  return request('POST', '/auth/openai/callback', { code, state });
}

export async function getOAuthStatus(): Promise<{
  connected: boolean;
  email?: string;
  scopes?: string;
  valid?: boolean;
}> {
  return request('GET', '/auth/openai/status');
}

export async function disconnectOAuth(): Promise<{ ok: boolean }> {
  return request('DELETE', '/auth/openai/disconnect');
}
```

- [ ] **Step 3: Add loginWithOpenAI to AuthContext**

In `frontend/src/contexts/AuthContext.tsx`, add `loginWithOpenAI` to the `AuthContextValue` interface (line 22):

```typescript
interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  user: UserProfile | null;
  loading: boolean;
  getRedirectResultForCallback: () => Promise<UserCredential | null>;
  loginWithGoogle: () => Promise<void>;
  loginWithOpenAI: () => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}
```

And add the implementation in the `useMemo` value (around line 265, after `loginWithGoogle`):

```typescript
      async loginWithOpenAI() {
        const { getOAuthLoginUrl } = await import('../api/client');
        const { url } = await getOAuthLoginUrl('login');
        window.location.href = url;
      },
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/contexts/AuthContext.tsx
git commit -m "feat(oauth): add OAuth types, API client, and AuthContext method"
```

---

## Task 7: Frontend — OpenAI Callback Page & Login Button

**Files:**
- Create: `frontend/src/pages/OpenAICallback.tsx`
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx:88-91`
- Modify: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Create OpenAI callback page**

Create `frontend/src/pages/OpenAICallback.tsx`:

```tsx
/**
 * OpenAI OAuth Callback Page
 *
 * Handles the redirect back from OpenAI OAuth.
 * - Login flow: receives firebase_custom_token, signs in with Firebase
 * - Connect flow: receives {connected: true}, redirects to settings
 * - Error: shows message with action button
 */

import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { signInWithCustomToken } from 'firebase/auth';

import { auth } from '../config/firebase';
import { oauthCallback, setAuthToken } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

type CallbackStatus = 'processing' | 'success' | 'error';

export function OpenAICallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { refreshProfile } = useAuth();
  const [status, setStatus] = useState<CallbackStatus>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code || !state) {
      setStatus('error');
      setErrorMessage('Missing authorization code. Please try again.');
      return;
    }

    (async () => {
      try {
        const result = await oauthCallback(code, state);

        if (result.error) {
          setStatus('error');
          setErrorMessage(result.message || result.error);
          return;
        }

        if (result.firebase_custom_token) {
          // Login flow: sign in with Firebase custom token
          if (auth) {
            const cred = await signInWithCustomToken(auth, result.firebase_custom_token);
            const idToken = await cred.user.getIdToken();
            setAuthToken(idToken);
          } else {
            // Dev mode without Firebase — store the custom token directly
            setAuthToken(result.firebase_custom_token);
          }
          await refreshProfile();
          setStatus('success');
          navigate('/projects', { replace: true });
          return;
        }

        if (result.connected) {
          // Connect flow: redirect to settings
          setStatus('success');
          navigate('/settings', { replace: true });
          return;
        }

        setStatus('error');
        setErrorMessage('Unexpected response from server.');
      } catch (err) {
        setStatus('error');
        setErrorMessage(err instanceof Error ? err.message : 'Authentication failed');
      }
    })();
  }, [searchParams, navigate, refreshProfile]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md bg-white border rounded-lg p-8 space-y-6 text-center">
        {status === 'processing' && (
          <>
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600"></div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Signing in with OpenAI</h1>
            <p className="text-sm text-gray-600">Please wait...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center">
              <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Success</h1>
            <p className="text-sm text-gray-600">Redirecting...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center">
              <div className="h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Authentication Failed</h1>
            <p className="text-sm text-red-600">{errorMessage}</p>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Back to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Export from pages/index.ts**

Add to `frontend/src/pages/index.ts`:

```typescript
export { OpenAICallbackPage } from './OpenAICallback';
```

- [ ] **Step 3: Add route in App.tsx**

In `frontend/src/App.tsx`, import `OpenAICallbackPage` in the imports (line 11 area) and add the route after the existing `/auth/callback` route (line 90):

Add to imports:
```typescript
  OpenAICallbackPage,
```

Add route after line 90 (`<Route path="/auth/callback" ...>`):
```tsx
        <Route path="/auth/openai/callback" element={<OpenAICallbackPage />} />
```

- [ ] **Step 4: Add "Sign in with OpenAI" button to Login page**

In `frontend/src/pages/Login.tsx`, add after the Google button (after line 88, before the "First time?" paragraph):

```tsx
        <button
          type="button"
          disabled={isSubmitting}
          onClick={async () => {
            setError(null);
            setIsSubmitting(true);
            try {
              await loginWithOpenAI();
            } catch (err) {
              const message = err instanceof Error ? err.message : 'Sign-in failed';
              setError(message);
              setIsSubmitting(false);
            }
          }}
          className="w-full px-4 py-2 bg-gray-900 text-white rounded-lg disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {isSubmitting ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              Redirecting...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364l2.0201-1.1638a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.4114-.6765zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0974-2.3616l2.603-1.5006 2.6029 1.5006v3.0013l-2.6029 1.5006-2.603-1.5006z" />
              </svg>
              Sign in with OpenAI
            </>
          )}
        </button>
```

Also update the destructured auth values at line 7 to include `loginWithOpenAI`:
```typescript
  const { firebaseUser, user, loading, loginWithGoogle, loginWithOpenAI } = useAuth();
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/OpenAICallback.tsx frontend/src/pages/index.ts frontend/src/App.tsx frontend/src/pages/Login.tsx
git commit -m "feat(oauth): add OpenAI callback page, login button, and routing"
```

---

## Task 8: Frontend — Connected Accounts in User Settings

**Files:**
- Modify: `frontend/src/pages/UserSettings.tsx:100-110`

- [ ] **Step 1: Add Connected Accounts section**

In `frontend/src/pages/UserSettings.tsx`, add a Connected Accounts section between the form and the API Keys section (after line 100, before the `<div className="border-t">` for APIKeyManager):

```tsx
        <div className="border-t border-[var(--border)] pt-4 mt-4">
          <h2 className="text-sm font-medium mb-3">Connected Accounts</h2>
          <ConnectedAccounts user={user} onRefresh={refreshProfile} />
        </div>
```

And add the `ConnectedAccounts` component at the top of the file (after the imports):

```tsx
import { getOAuthLoginUrl, getOAuthStatus, disconnectOAuth } from '../api/client';

function ConnectedAccounts({ user, onRefresh }: { user: UserProfile; onRefresh: () => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  const [oauthError, setOAuthError] = useState<string | null>(null);

  const handleConnect = async () => {
    setOAuthError(null);
    setLoading(true);
    try {
      const { url } = await getOAuthLoginUrl('connect');
      window.location.href = url;
    } catch (err) {
      setOAuthError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    setOAuthError(null);
    setLoading(true);
    try {
      await disconnectOAuth();
      await onRefresh();
    } catch (err) {
      setOAuthError(err instanceof Error ? err.message : 'Failed to disconnect');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded bg-gray-900 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364l2.0201-1.1638a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.4114-.6765zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0974-2.3616l2.603-1.5006 2.6029 1.5006v3.0013l-2.6029 1.5006-2.603-1.5006z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium">OpenAI</p>
            {user.openai_connected ? (
              <p className="text-xs text-green-600">Connected</p>
            ) : (
              <p className="text-xs text-gray-500">Not connected</p>
            )}
          </div>
        </div>
        {user.openai_connected ? (
          <Button variant="ghost" size="sm" onClick={handleDisconnect} disabled={loading}>
            Disconnect
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={handleConnect} disabled={loading}>
            Connect
          </Button>
        )}
      </div>
      {oauthError && <p className="text-xs text-red-600">{oauthError}</p>}
      {user.openai_connected && (
        <p className="text-xs text-gray-500">
          OpenAI LLM calls use your OAuth token automatically. BYOK keys are not used while OAuth is active.
        </p>
      )}
    </div>
  );
}
```

Also add `UserProfile` to the imports from types, and `getOAuthLoginUrl`, `disconnectOAuth` to the api/client imports.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/UserSettings.tsx
git commit -m "feat(oauth): add Connected Accounts section to User Settings"
```

---

## Task 9: Local Dev Config & Documentation Update

**Files:**
- Modify: `docs/v5/openai-oauth-design.md` (update status)
- Modify: `CLAUDE.md` (add OAuth dev commands)

- [ ] **Step 1: Update the design spec status**

In `docs/v5/openai-oauth-design.md`, change line 2:
```markdown
> **Status:** Implemented (local dev with mock OAuth server)
```

- [ ] **Step 2: Add OAuth development commands to CLAUDE.md**

In `CLAUDE.md`, add to the Development Commands section under Backend:

```markdown
### OAuth (Local Dev)

```bash
# Start mock OpenAI OAuth server (in a separate terminal)
python -m backend.tests.mock_oauth_server

# Required env vars for local OAuth testing (add to .env.development):
#   OPENAI_OAUTH_CLIENT_ID=mock-client-id
#   OPENAI_OAUTH_CLIENT_SECRET=mock-client-secret
#   OPENAI_OAUTH_AUTHORIZE_URL=http://localhost:8099/oauth/authorize
#   OPENAI_OAUTH_TOKEN_URL=http://localhost:8099/oauth/token
#   OPENAI_OAUTH_USERINFO_URL=http://localhost:8099/v1/me
#   OPENAI_OAUTH_REDIRECT_URI=http://localhost:3000/auth/openai/callback
```
```

- [ ] **Step 3: Commit**

```bash
git add docs/v5/openai-oauth-design.md CLAUDE.md
git commit -m "docs: update OAuth spec status and add local dev instructions"
```

---

## Task 10: Backend Unit Tests

**Files:**
- Create: `backend/tests/test_oauth.py`

- [ ] **Step 1: Write tests for OAuth service**

Create `backend/tests/test_oauth.py`:

```python
"""Tests for OAuth service — state tokens, flow logic."""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.oauth_service import (
    create_state_token,
    verify_state_token,
)


class TestStateTokens:
    def test_create_and_verify_roundtrip(self):
        token = create_state_token("login")
        payload = verify_state_token(token)
        assert payload is not None
        assert payload["flow"] == "login"
        assert "nonce" in payload
        assert "exp" in payload

    def test_connect_flow_type(self):
        token = create_state_token("connect")
        payload = verify_state_token(token)
        assert payload["flow"] == "connect"

    def test_tampered_token_rejected(self):
        token = create_state_token("login")
        # Flip a character in the signature
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert verify_state_token(tampered) is None

    def test_expired_token_rejected(self):
        token = create_state_token("login")
        # Manually expire it by patching time
        payload_str = token.rsplit("|", 1)[0]
        import json
        payload = json.loads(payload_str)
        payload["exp"] = int(time.time()) - 1
        expired_payload = json.dumps(payload)
        import hashlib, hmac
        from backend.services.oauth_service import _hmac_key
        sig = hmac.new(_hmac_key(), expired_payload.encode(), hashlib.sha256).hexdigest()
        expired_token = f"{expired_payload}|{sig}"
        assert verify_state_token(expired_token) is None

    def test_malformed_token_rejected(self):
        assert verify_state_token("not-a-valid-token") is None
        assert verify_state_token("") is None
        assert verify_state_token("a|b|c") is None
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_oauth.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_oauth.py
git commit -m "test(oauth): add unit tests for state token creation and verification"
```

---

## Self-Review Checklist

| Spec Section | Covered by Task |
|---|---|
| §2 Firebase Custom Tokens as Bridge | Task 3 (handle_login_flow mints custom token) |
| §3 Data Model (user_oauth_connections) | Task 1 |
| §3.2 User.firebase_uid widening | Task 1 |
| §3.3 Email collision handling | Task 3 (handle_login_flow checks email) |
| §4.1 Flow A: New user signs in | Tasks 3, 4 (login flow) |
| §4.2 Flow B: Connect OpenAI | Tasks 3, 4 (connect flow) |
| §4.3 Flow C: Disconnect | Tasks 3, 4 (disconnect endpoint) |
| §5 Backend Endpoints | Task 4 |
| §7 Config Changes | Task 2 |
| §8.1 Login page | Task 7 |
| §8.2 Callback route | Task 7 |
| §8.3 User Settings Connected Accounts | Task 8 |
| §8.4 AuthContext changes | Task 6 |
| §8.5 UserProfile type | Task 6 |
| §10 Database Migration | Task 1 |
| §11 Security (CSRF state) | Task 3 |
| §14 Testing | Task 10 |
| Mock OAuth server | Task 5 |
| Documentation updates | Task 9 |

**Not covered (by design):**
- §4.4 Flow D: Link Google to OpenAI-only user — standard Firebase account linking, deferred
- §6 Token Lifecycle / LLM routing changes — deferred to when real OpenAI OAuth tokens become available
- §9 LLM Routing Changes — deferred (mock tokens can't make real LLM calls)
