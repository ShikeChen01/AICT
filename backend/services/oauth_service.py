"""
OAuthService — OpenAI OAuth flow: state tokens, code exchange, user provisioning.

State tokens are HMAC-signed, self-contained CSRF tokens.
Tokens, once exchanged, are stored encrypted (Fernet) in UserOAuthConnection.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import User, UserOAuthConnection
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# State token TTL in seconds (10 minutes)
_STATE_TTL = 600


# ── HMAC key derivation ─────────────────────────────────────────────

def _hmac_key() -> bytes:
    """Derive a stable HMAC key from settings."""
    source = settings.secret_encryption_key or settings.api_token
    return hashlib.sha256(source.encode()).digest()


# ── State token helpers ─────────────────────────────────────────────

def create_state_token(flow: str) -> str:
    """
    Mint a signed CSRF state token.

    Format: ``{base64url-json-payload}|{hex-hmac}``
    Payload contains: flow, nonce, exp (unix timestamp).
    """
    payload = {
        "flow": flow,
        "nonce": secrets.token_hex(16),
        "exp": int(time.time()) + _STATE_TTL,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_bytes = payload_json.encode()
    sig = hmac.new(_hmac_key(), payload_bytes, hashlib.sha256).hexdigest()
    # Encode payload as hex so it is URL-safe without padding concerns
    payload_hex = payload_bytes.hex()
    return f"{payload_hex}|{sig}"


def verify_state_token(token: str) -> dict:
    """
    Verify and decode a state token.

    Returns the payload dict on success.
    Raises ValueError with a descriptive message on any failure.
    """
    try:
        payload_hex, sig = token.split("|", 1)
    except ValueError as exc:
        raise ValueError("Malformed state token: missing separator") from exc

    payload_bytes = bytes.fromhex(payload_hex)
    expected_sig = hmac.new(_hmac_key(), payload_bytes, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("State token signature invalid")

    payload = json.loads(payload_bytes.decode())
    if int(time.time()) > payload.get("exp", 0):
        raise ValueError("State token expired")

    return payload


# ── Authorization URL ───────────────────────────────────────────────

def build_authorize_url(flow: str) -> str:
    """Build the OpenAI OAuth authorization URL including a fresh state token."""
    state = create_state_token(flow)
    params = httpx.QueryParams({
        "client_id": settings.openai_oauth_client_id,
        "redirect_uri": settings.openai_oauth_redirect_uri,
        "response_type": "code",
        "scope": settings.openai_oauth_scopes,
        "state": state,
    })
    return f"{settings.openai_oauth_authorize_url}?{params}"


# ── Token exchange & userinfo ───────────────────────────────────────

async def exchange_code_for_tokens(code: str) -> dict:
    """POST to the token endpoint and return the token response dict."""
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
    """GET the userinfo endpoint and return the profile dict."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.openai_oauth_userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


# ── Encryption helpers ──────────────────────────────────────────────

def _get_fernet():
    """Return a Fernet instance if a key is configured, else None."""
    key = settings.secret_encryption_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        logger.warning("Fernet init failed, falling back to plaintext: %s", exc)
        return None


def _encrypt(value: str) -> str:
    """Encrypt value with Fernet; falls back to plaintext if no key configured."""
    fernet = _get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    """Decrypt value with Fernet; falls back to returning value as-is."""
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception as exc:
        logger.warning("Failed to decrypt OAuth token: %s", exc)
        return value


# ── Upsert helper ───────────────────────────────────────────────────

async def _upsert_oauth_connection(
    db: AsyncSession,
    user: User,
    provider_user_id: str,
    provider_email: str | None,
    token_data: dict,
) -> UserOAuthConnection:
    """Create or update the UserOAuthConnection row for openai."""
    access_token = _encrypt(token_data.get("access_token", ""))
    refresh_token_raw = token_data.get("refresh_token")
    refresh_token = _encrypt(refresh_token_raw) if refresh_token_raw else None
    scopes = token_data.get("scope") or settings.openai_oauth_scopes

    # Expiry: token_data may include expires_in (seconds) or expires_at (unix ts)
    token_expires_at: datetime | None = None
    if "expires_at" in token_data:
        try:
            token_expires_at = datetime.fromtimestamp(
                float(token_data["expires_at"]), tz=timezone.utc
            )
        except Exception:
            pass
    elif "expires_in" in token_data:
        try:
            token_expires_at = datetime.fromtimestamp(
                time.time() + float(token_data["expires_in"]), tz=timezone.utc
            )
        except Exception:
            pass

    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )
    conn = result.scalar_one_or_none()

    if conn is None:
        conn = UserOAuthConnection(
            user_id=user.id,
            provider="openai",
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
            is_valid=True,
        )
        db.add(conn)
    else:
        conn.provider_user_id = provider_user_id
        conn.provider_email = provider_email
        conn.access_token = access_token
        conn.refresh_token = refresh_token
        conn.token_expires_at = token_expires_at
        conn.scopes = scopes
        conn.is_valid = True

    await db.commit()
    await db.refresh(conn)
    return conn


# ── Main flow handlers ──────────────────────────────────────────────

async def handle_login_flow(db: AsyncSession, code: str) -> dict:
    """
    Full OAuth login flow:
    1. Exchange code for tokens
    2. Fetch userinfo
    3. Handle email collision with non-OpenAI accounts
    4. Find or create User with firebase_uid="openai:{provider_user_id}"
    5. Upsert UserOAuthConnection
    6. Mint Firebase Custom Token
    7. Return {"firebase_custom_token": "..."}
    """
    token_data = await exchange_code_for_tokens(code)
    userinfo = await fetch_userinfo(token_data["access_token"])

    provider_user_id = str(userinfo.get("id") or userinfo.get("sub") or "")
    email = userinfo.get("email") or ""
    display_name = userinfo.get("name") or userinfo.get("display_name") or email
    firebase_uid = f"openai:{provider_user_id}"

    # Check for email collision: email exists but belongs to a non-OpenAI account
    if email:
        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None and not existing.firebase_uid.startswith("openai:"):
            return {
                "error": "email_exists",
                "message": (
                    f"An account with email {email!r} already exists. "
                    "Please log in with your original method and connect OpenAI from Settings."
                ),
            }

    # Find or create the User
    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Created new user for OpenAI OAuth login: firebase_uid=%s", firebase_uid)
    else:
        logger.info("Existing user logged in via OpenAI OAuth: firebase_uid=%s", firebase_uid)

    await _upsert_oauth_connection(
        db, user, provider_user_id, email or None, token_data
    )

    # Mint Firebase Custom Token
    try:
        from backend.core.auth import _init_firebase
        from firebase_admin import auth as firebase_auth

        _init_firebase()
        raw_token = firebase_auth.create_custom_token(firebase_uid)
        # create_custom_token returns bytes; decode if needed
        custom_token = raw_token.decode() if isinstance(raw_token, bytes) else raw_token
    except Exception as exc:
        logger.error("Failed to mint Firebase custom token: %s", exc)
        raise RuntimeError("Could not create Firebase custom token") from exc

    return {"firebase_custom_token": custom_token}


async def handle_connect_flow(db: AsyncSession, user: User, code: str) -> dict:
    """
    Connect an existing AICT account to OpenAI OAuth.
    Exchanges code, fetches userinfo, upserts the connection row.
    Returns {"connected": True}.
    """
    token_data = await exchange_code_for_tokens(code)
    userinfo = await fetch_userinfo(token_data["access_token"])

    provider_user_id = str(userinfo.get("id") or userinfo.get("sub") or "")
    provider_email = userinfo.get("email") or None

    await _upsert_oauth_connection(
        db, user, provider_user_id, provider_email, token_data
    )
    logger.info(
        "User %s connected OpenAI OAuth (provider_user_id=%s)",
        user.id,
        provider_user_id,
    )
    return {"connected": True}


async def get_connection_status(db: AsyncSession, user_id) -> dict:
    """Return current OAuth connection status for a user."""
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user_id,
            UserOAuthConnection.provider == "openai",
        )
    )
    conn = result.scalar_one_or_none()

    if conn is None:
        return {"connected": False, "email": None, "scopes": None, "valid": None}

    return {
        "connected": True,
        "email": conn.provider_email,
        "scopes": conn.scopes,
        "valid": conn.is_valid,
    }


async def disconnect(db: AsyncSession, user: User) -> None:
    """
    Remove the OpenAI OAuth connection for a user.

    Raises ValueError if OpenAI OAuth is the user's only authentication method.
    """
    if user.firebase_uid.startswith("openai:"):
        raise ValueError(
            "Cannot disconnect OpenAI OAuth: it is your only authentication method. "
            "Link a password or another provider first."
        )

    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )
    conn = result.scalar_one_or_none()

    if conn is not None:
        await db.delete(conn)
        await db.commit()
        logger.info("Disconnected OpenAI OAuth for user %s", user.id)
    else:
        logger.info("disconnect called but no connection found for user %s", user.id)
