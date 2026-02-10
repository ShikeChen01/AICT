"""
Aggregated internal API router (for agent tool calls).
Individual route modules will be added as services are implemented.
"""

from fastapi import APIRouter

internal_router = APIRouter()


@internal_router.get("/health", tags=["internal-health"])
async def internal_health_check():
    return {"status": "ok"}
