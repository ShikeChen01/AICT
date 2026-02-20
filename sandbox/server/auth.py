"""Token-based authentication for sandbox server endpoints."""

from fastapi import HTTPException, Query, Request, status

from config import AUTH_TOKEN


def _token_valid(token: str) -> bool:
    if not AUTH_TOKEN:
        return True  # no token configured → open (dev mode only)
    return token == AUTH_TOKEN


async def require_token(request: Request) -> None:
    """FastAPI dependency: validate Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    if not _token_valid(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def validate_ws_token(token: str = Query(default="")) -> str:
    """FastAPI dependency for WebSocket token (passed as query param)."""
    if not _token_valid(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token
