"""
OpenAI OAuth endpoints.

GET  /auth/openai/login          — initiate OAuth flow, returns redirect URL
POST /auth/openai/callback       — exchange code, complete login or connect
GET  /auth/openai/status         — connection status (protected)
DELETE /auth/openai/disconnect   — remove connection (protected)
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import _verify_firebase_token, get_current_user
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.schemas.oauth import (
    OAuthCallbackRequest,
    OAuthLoginResponse,
    OAuthStatusResponse,
)
from backend.services import oauth_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/openai", tags=["oauth"])


@router.get("/login", response_model=OAuthLoginResponse)
async def initiate_login(flow: str = "login") -> OAuthLoginResponse:
    """
    Return the OpenAI OAuth authorization URL.

    ``flow`` must be ``login`` or ``connect``.
    Requires ``openai_oauth_client_id`` to be configured.
    """
    if not settings.openai_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI OAuth is not configured on this server.",
        )
    if flow not in ("login", "connect"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="flow must be 'login' or 'connect'",
        )
    url = oauth_service.build_authorize_url(flow)
    return OAuthLoginResponse(url=url)


@router.post("/callback")
async def oauth_callback(
    body: OAuthCallbackRequest,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle the OAuth callback from OpenAI.

    - Verifies the CSRF state token.
    - If flow=connect and an Authorization header is present, resolves the
      current user from their Firebase ID token and connects their account.
    - If flow=login, performs the full login flow and returns a Firebase
      Custom Token for the client to sign in with.
    """
    # Verify CSRF state token
    try:
        state_payload = oauth_service.verify_state_token(body.state)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    flow = state_payload.get("flow", "login")

    try:
        if flow == "connect" and authorization:
            # Resolve the calling user from their Firebase ID token
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Authorization header format",
                )
            token = authorization.removeprefix("Bearer ").strip()
            decoded = _verify_firebase_token(token)
            if decoded is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Firebase token",
                )

            from sqlalchemy import select
            from backend.db.models import User

            result = await db.execute(
                select(User).where(User.firebase_uid == decoded.get("uid"))
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            result_data = await oauth_service.handle_connect_flow(db, user, body.code)
            return result_data

        # login flow
        result_data = await oauth_service.handle_login_flow(db, body.code)
        return result_data

    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Upstream OAuth request failed: status=%s body=%s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider returned an error. Please try again.",
        ) from exc


@router.get("/status", response_model=OAuthStatusResponse)
async def connection_status(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthStatusResponse:
    """Return the OpenAI OAuth connection status for the current user."""
    data = await oauth_service.get_connection_status(db, current_user.id)
    return OAuthStatusResponse(**data)


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_openai(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the OpenAI OAuth connection for the current user."""
    try:
        await oauth_service.disconnect(db, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
