"""
Authentication utilities.

Single user per instance; token-based Bearer auth.
"""

from fastapi import Header, HTTPException, status

from backend.config import settings


async def verify_token(authorization: str = Header(...)) -> bool:
    """
    Verify Bearer token from Authorization header.
    Used for all public REST API endpoints.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return True


def verify_ws_token(token: str | None) -> bool:
    """
    Verify token for WebSocket connections.
    Token passed as query parameter: /ws?token=<API_TOKEN>
    """
    if token is None:
        return False
    return token == settings.api_token


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
