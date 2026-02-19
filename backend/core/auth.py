"""Authentication utilities.

Supports Firebase ID tokens with an API token fallback.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import User
from backend.db.session import get_db
from backend.logging.my_logger import get_logger

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except Exception:  # pragma: no cover - dependency may be absent in local tests
    firebase_admin = None
    firebase_auth = None
    credentials = None


_firebase_ready = False
logger = get_logger(__name__)


def _token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]
    return f"len={len(token)},sha256={digest}"


def _request_context(request: Request | None) -> str:
    if request is None:
        return "method=unknown path=unknown"
    return f"method={request.method} path={request.url.path}"


def _error_summary(exc: Exception, max_len: int = 160) -> str:
    message = str(exc).replace("\n", " ").strip()
    if len(message) > max_len:
        message = message[:max_len] + "..."
    return f"{exc.__class__.__name__}: {message}"


def _resolve_credentials_path() -> Path | None:
    raw_path = (settings.firebase_credentials_path or "").strip()
    if not raw_path:
        raw_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _init_firebase() -> bool:
    global _firebase_ready
    if _firebase_ready:
        return True
    if firebase_admin is None or credentials is None:
        return False
    try:
        if not firebase_admin._apps:
            options = (
                {"projectId": settings.firebase_project_id}
                if settings.firebase_project_id
                else None
            )
            credentials_path = _resolve_credentials_path()
            if credentials_path:
                if not credentials_path.exists():
                    logger.warning(
                        "Firebase credentials file not found: %s",
                        credentials_path,
                    )
                    firebase_admin.initialize_app(options=options)
                else:
                    cred = credentials.Certificate(str(credentials_path))
                    firebase_admin.initialize_app(cred, options=options)
            else:
                # Fallback to Application Default Credentials (useful for Cloud Run).
                firebase_admin.initialize_app(options=options)
        _firebase_ready = True
        return True
    except Exception as exc:
        logger.warning("Firebase initialization failed: %s", exc)
        return False


def _verify_firebase_token(token: str, request_context: str = "method=unknown path=unknown") -> dict | None:
    if not _init_firebase() or firebase_auth is None:
        logger.warning(
            "Firebase verification unavailable (%s, token=%s)",
            request_context,
            _token_fingerprint(token),
        )
        return None
    try:
        decoded = firebase_auth.verify_id_token(token)
        logger.debug(
            "Firebase token verified (%s, token=%s)",
            request_context,
            _token_fingerprint(token),
        )
        return decoded
    except Exception as exc:
        logger.warning(
            "Firebase token verification failed (%s, token=%s, error=%s)",
            request_context,
            _token_fingerprint(token),
            _error_summary(exc),
        )
        return None


async def verify_token(
    request: Request,
    authorization: str = Header(...),
) -> bool:
    """Verify bearer auth for API endpoints."""
    request_context = _request_context(request)
    if not authorization.startswith("Bearer "):
        logger.warning("Authorization header malformed (%s)", request_context)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()
    token_fingerprint = _token_fingerprint(token)
    if token == settings.api_token:
        logger.info(
            "Auth accepted via api_token (%s, token=%s)",
            request_context,
            token_fingerprint,
        )
        return True
    decoded = _verify_firebase_token(token, request_context=request_context)
    if decoded is not None:
        logger.info(
            "Auth accepted via firebase_token (%s, token=%s, uid_present=%s)",
            request_context,
            token_fingerprint,
            bool(decoded.get("uid")),
        )
        return True
    logger.warning(
        "Auth rejected (%s, token=%s, source=unknown)",
        request_context,
        token_fingerprint,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )


async def get_current_user(
    request: Request,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify Firebase ID token and return/create the app user."""
    request_context = _request_context(request)
    if not authorization.startswith("Bearer "):
        logger.warning("Authorization header malformed in get_current_user (%s)", request_context)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()
    token_fingerprint = _token_fingerprint(token)
    if token == settings.api_token:
        result = await db.execute(select(User).where(User.firebase_uid == "local-api-token-user"))
        local_user = result.scalar_one_or_none()
        if local_user:
            logger.info(
                "Resolved current user via api_token (%s, token=%s, resolution=existing_user)",
                request_context,
                token_fingerprint,
            )
            return local_user
        local_user = User(
            firebase_uid="local-api-token-user",
            email="local-user@aict.local",
            display_name="Local User",
        )
        db.add(local_user)
        await db.commit()
        await db.refresh(local_user)
        logger.info(
            "Resolved current user via api_token (%s, token=%s, resolution=created_user)",
            request_context,
            token_fingerprint,
        )
        return local_user

    decoded = _verify_firebase_token(token, request_context=request_context)
    if decoded is None:
        logger.warning(
            "Rejected firebase_token in get_current_user (%s, token=%s)",
            request_context,
            token_fingerprint,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )

    firebase_uid = decoded.get("uid")
    if not firebase_uid:
        logger.warning(
            "Firebase token missing uid (%s, token=%s)",
            request_context,
            token_fingerprint,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token missing uid",
        )

    email_present = bool(decoded.get("email"))
    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()
    if user:
        logger.info(
            "Resolved current user via firebase_token (%s, token=%s, uid_present=%s, email_present=%s, resolution=existing_user)",
            request_context,
            token_fingerprint,
            True,
            email_present,
        )
        return user

    user = User(
        firebase_uid=firebase_uid,
        email=str(decoded.get("email") or ""),
        display_name=decoded.get("name"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(
        "Resolved current user via firebase_token (%s, token=%s, uid_present=%s, email_present=%s, resolution=created_user)",
        request_context,
        token_fingerprint,
        True,
        email_present,
    )
    return user


def verify_ws_token(token: str | None) -> bool:
    """Verify websocket auth token."""
    if token is None:
        return False
    if token == settings.api_token:
        return True
    return _verify_firebase_token(token) is not None


async def verify_internal_api_token(
    request: Request,
    authorization: str = Header(...),
) -> bool:
    """Verify internal API Bearer token (shared API token only)."""
    request_context = _request_context(request)
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.api_token:
        logger.warning(
            "Internal auth rejected (%s, token=%s)",
            request_context,
            _token_fingerprint(token),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API token",
        )
    return True


async def verify_agent_request(
    _internal_auth: bool = Depends(verify_internal_api_token),
    x_agent_id: str = Header(...),
) -> str:
    """
    Verify request is from an authenticated internal caller and includes a valid X-Agent-ID.
    Agent existence is validated at service layer.
    """
    if not x_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Agent-ID header",
        )
    try:
        parsed = uuid.UUID(x_agent_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Agent-ID header",
        ) from exc
    return str(parsed)
