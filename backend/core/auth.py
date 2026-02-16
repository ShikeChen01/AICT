"""Authentication utilities.

Supports Firebase ID tokens with an API token fallback.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import User
from backend.db.session import get_db

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except Exception:  # pragma: no cover - dependency may be absent in local tests
    firebase_admin = None
    firebase_auth = None
    credentials = None


_firebase_ready = False
logger = logging.getLogger(__name__)


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


def _verify_firebase_token(token: str) -> dict | None:
    if not _init_firebase() or firebase_auth is None:
        return None
    try:
        return firebase_auth.verify_id_token(token)
    except Exception:
        return None


async def verify_token(authorization: str = Header(...)) -> bool:
    """Verify bearer auth for API endpoints."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token == settings.api_token:
        return True
    if _verify_firebase_token(token) is not None:
        return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )


async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify Firebase ID token and return/create the app user."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token == settings.api_token:
        result = await db.execute(select(User).where(User.firebase_uid == "local-api-token-user"))
        local_user = result.scalar_one_or_none()
        if local_user:
            return local_user
        local_user = User(
            firebase_uid="local-api-token-user",
            email="local-user@aict.local",
            display_name="Local User",
        )
        db.add(local_user)
        await db.commit()
        await db.refresh(local_user)
        return local_user

    decoded = _verify_firebase_token(token)
    if decoded is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )

    firebase_uid = decoded.get("uid")
    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token missing uid",
        )

    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(
        firebase_uid=firebase_uid,
        email=str(decoded.get("email") or ""),
        display_name=decoded.get("name"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def verify_ws_token(token: str | None) -> bool:
    """Verify websocket auth token."""
    if token is None:
        return False
    if token == settings.api_token:
        return True
    return _verify_firebase_token(token) is not None


async def verify_agent_request(x_agent_id: str = Header(...)) -> str:
    """
    Verify request is from a valid agent (internal API).
    The X-Agent-ID header must be present.
    Actual agent existence validated at service layer.
    """
    if not x_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Agent-ID header",
        )
    return x_agent_id
