"""
Aggregated v1 API router.
"""

from fastapi import APIRouter

from backend.api.v1.agents import router as agents_router
from backend.api.v1.attachments import router as attachments_router
from backend.api.v1.auth import router as auth_router
from backend.api.v1.diagnostics import router as diagnostics_router
from backend.api.v1.documents import router as documents_router
from backend.api.v1.messages import router as messages_router
from backend.api.v1.prompt_blocks import router as prompt_blocks_router
from backend.api.v1.project_secrets import router as project_secrets_router
from backend.api.v1.repositories import router as repositories_router
from backend.api.v1.sessions import router as sessions_router
from backend.api.v1.tasks import router as tasks_router
from backend.api.v1.templates import router as templates_router
from backend.api.v1.tool_configs import router as tool_configs_router

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@api_router.get("/health/workers", tags=["health"])
async def worker_health():
    """Diagnostic: returns WorkerManager runtime status (started, worker_count, agent_ids)."""
    from backend.workers.worker_manager import get_worker_manager
    return get_worker_manager().get_status()


# Include feature routers
api_router.include_router(agents_router)
api_router.include_router(attachments_router)
api_router.include_router(auth_router)
api_router.include_router(diagnostics_router)
api_router.include_router(documents_router)
api_router.include_router(messages_router)
api_router.include_router(prompt_blocks_router)
api_router.include_router(project_secrets_router)
api_router.include_router(repositories_router)
api_router.include_router(sessions_router)
api_router.include_router(tasks_router)
api_router.include_router(templates_router)
api_router.include_router(tool_configs_router)
