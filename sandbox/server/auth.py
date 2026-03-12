"""Authentication for the sandbox server.

Supports two auth modes:
1. Master token (AUTH_TOKEN) — used by backend→sandbox calls
2. JWT (SANDBOX_JWT_SECRET) — used by frontend→sandbox direct access
"""
from __future__ import annotations

import jwt as pyjwt
from fastapi import HTTPException, Query, Request, status

from config import AUTH_TOKEN, SANDBOX_JWT_SECRET, SANDBOX_ID


def _token_valid(token: str) -> bool:
    """Validate a token against AUTH_TOKEN or JWT."""
    if not token:
        return False

    # 1. Check master token (backend→sandbox calls)
    if AUTH_TOKEN and token == AUTH_TOKEN:
        return True

    # 2. Open mode (no auth configured)
    if not AUTH_TOKEN and not SANDBOX_JWT_SECRET:
        return True

    # 3. Check JWT (frontend→sandbox direct access)
    if SANDBOX_JWT_SECRET:
        try:
            payload = pyjwt.decode(token, SANDBOX_JWT_SECRET, algorithms=["HS256"])
            # If SANDBOX_ID is configured, verify it matches
            if SANDBOX_ID and payload.get("sandbox_id") != SANDBOX_ID:
                return False
            return True
        except (pyjwt.InvalidTokenError, pyjwt.ExpiredSignatureError):
            pass

    return False


async def require_token(request: Request) -> None:
    """FastAPI dependency: verify Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        if not AUTH_TOKEN and not SANDBOX_JWT_SECRET:
            return  # Open mode
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    if not _token_valid(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def validate_ws_token(token: str = Query(...)) -> None:
    """FastAPI dependency: verify token from WebSocket query param."""
    if not _token_valid(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
