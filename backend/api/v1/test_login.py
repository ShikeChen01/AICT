"""Test login endpoint — development/testing use only.

Validates a fixed email/password pair from .env.development and returns
the shared api_token so the frontend can authenticate without Firebase.

Guards:
- Disabled (404) unless TEST_LOGIN_ENABLED=true in the environment.
- Per-IP rate limit: 30 attempts per 60-second window (in-memory).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.config import settings
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["test-login"])

_rate_store: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()
_MAX_ATTEMPTS = 30
_WINDOW_S = 60


def _enforce_rate_limit(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        window = _rate_store[ip]
        while window and now - window[0] > _WINDOW_S:
            window.popleft()
        if len(window) >= _MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )
        window.append(now)


class _LoginRequest(BaseModel):
    email: str
    password: str


class _LoginResponse(BaseModel):
    token: str


@router.post("/testfads89213xlogin", response_model=_LoginResponse)
async def test_login(body: _LoginRequest, request: Request) -> _LoginResponse:
    if not settings.test_login_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    client_ip = request.client.host if request.client else "unknown"
    _enforce_rate_limit(client_ip)

    credentials_ok = (
        body.email == settings.test_login_email
        and body.password == settings.test_login_password
    )
    if not credentials_ok:
        logger.warning("Test login: invalid credentials (ip=%s)", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    logger.info("Test login: success (ip=%s)", client_ip)
    return _LoginResponse(token=settings.api_token)
