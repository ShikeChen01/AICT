"""
Aggregated internal API router (for agent tool calls).
Individual route modules will be added as services are implemented.
"""

from fastapi import APIRouter

from backend.api_internal.files import router as files_router
from backend.api_internal.git import router as git_router
from backend.api_internal.lifecycle import router as lifecycle_router
from backend.api_internal.tasks import router as tasks_router
from backend.api_internal.tickets import router as tickets_router

internal_router = APIRouter()


@internal_router.get("/health", tags=["internal-health"])
async def internal_health_check():
    return {"status": "ok"}


internal_router.include_router(lifecycle_router)
internal_router.include_router(git_router)
internal_router.include_router(files_router)
internal_router.include_router(tasks_router)
internal_router.include_router(tickets_router)
