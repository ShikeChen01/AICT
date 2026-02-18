"""
Aggregated v1 API router.
"""

from fastapi import APIRouter

from backend.api.v1.agents import router as agents_router
from backend.api.v1.auth import router as auth_router
from backend.api.v1.messages import router as messages_router
from backend.api.v1.repositories import router as repositories_router
from backend.api.v1.sessions import router as sessions_router
from backend.api.v1.tasks import router as tasks_router

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# Include feature routers
api_router.include_router(agents_router)
api_router.include_router(auth_router)
api_router.include_router(messages_router)
api_router.include_router(repositories_router)
api_router.include_router(sessions_router)
api_router.include_router(tasks_router)
