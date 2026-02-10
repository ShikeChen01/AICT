"""
Aggregated v1 API router.
Individual route modules will be added as services are implemented.
"""

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
