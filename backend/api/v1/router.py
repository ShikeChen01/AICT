"""
Aggregated v1 API router.
"""

from fastapi import APIRouter

from backend.api.v1.agents import router as agents_router
from backend.api.v1.chat import router as chat_router
from backend.api.v1.projects import router as projects_router
from backend.api.v1.tasks import router as tasks_router
from backend.api.v1.tickets import router as tickets_router

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# Include feature routers
api_router.include_router(agents_router)
api_router.include_router(chat_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
api_router.include_router(tickets_router)
