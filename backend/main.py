"""
AICT Backend — FastAPI application entry point.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.api_internal.router import internal_router
from backend.config import settings
from backend.core.error_handlers import aict_exception_handler
from backend.core.exceptions import AICTException
from backend.db.session import AsyncSessionLocal
from backend.services.orchestrator import (
    initialize_graph_runtime,
    shutdown_graph_runtime,
)
from backend.services.repo_provisioning import RepoProvisioningService
from backend.websocket.endpoint import router as ws_router

logger = logging.getLogger(__name__)


async def _provision_repositories_on_startup() -> None:
    if not settings.provision_repos_on_startup:
        return

    try:
        async with AsyncSessionLocal() as session:
            service = RepoProvisioningService()
            await service.provision_all_projects(session)
    except Exception as exc:
        # Startup should stay available even if provisioning is skipped.
        logger.warning("Repository provisioning skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await initialize_graph_runtime()
    await _provision_repositories_on_startup()
    yield
    # Shutdown
    await shutdown_graph_runtime()


app = FastAPI(title="AICT Backend", version="0.1.0", lifespan=lifespan)

# CORS — allow all in development; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AICTException, aict_exception_handler)

# Public API
app.include_router(api_router, prefix="/api/v1")

# Internal API (agent tools)
app.include_router(internal_router, prefix="/internal/agent")

# WebSocket endpoint
app.include_router(ws_router)
