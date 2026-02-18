"""
AICT Backend — FastAPI application entry point.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
from collections.abc import Awaitable

from backend.config import settings
from backend.core.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.v1.router import api_router
from backend.api_internal.router import internal_router
from backend.core.error_handlers import aict_exception_handler
from backend.core.exceptions import AICTException
from backend.db.migration_runner import run_startup_migrations
from backend.db.session import AsyncSessionLocal
from backend.workers.worker_manager import get_worker_manager
from backend.services.repo_provisioning import RepoProvisioningService
from backend.websocket.endpoint import router as ws_router

logger = logging.getLogger(__name__)

# Track background tasks
_background_tasks: list[asyncio.Task] = []


async def _run_startup_step(name: str, step: Awaitable[None]) -> None:
    """
    Run a startup step with timeout and soft-fail behavior.
    """
    try:
        await asyncio.wait_for(step, timeout=settings.startup_step_timeout_seconds)
    except TimeoutError:
        logger.warning(
            "Startup step timed out and was skipped: %s (timeout=%ss)",
            name,
            settings.startup_step_timeout_seconds,
        )
    except Exception as exc:
        logger.warning("Startup step failed and was skipped: %s (%s)", name, exc)


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


async def _start_worker_manager() -> None:
    """Start WorkerManager: MessageRouter + AgentWorkers per agent."""
    manager = get_worker_manager()
    await manager.start()
    logger.info("WorkerManager started")


async def _run_startup_migrations() -> None:
    """Run database migrations before starting background workers."""
    if not settings.auto_run_migrations_on_startup:
        return
    await asyncio.to_thread(run_startup_migrations)
    logger.info("Database migrations are up to date")


async def _stop_background_tasks() -> None:
    """Stop all background tasks gracefully."""
    manager = get_worker_manager()
    await manager.stop()

    for task in _background_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    _background_tasks.clear()
    logger.info("Background tasks stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _run_startup_step("run_startup_migrations", _run_startup_migrations())
    await _run_startup_step("provision_repositories_on_startup", _provision_repositories_on_startup())
    await _run_startup_step("start_worker_manager", _start_worker_manager())
    yield
    # Shutdown
    await _stop_background_tasks()


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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.
    
    Logs the full exception and returns a structured JSON error response
    instead of an HTML 500 error page.
    """
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    
    error_type = type(exc).__name__
    error_msg = str(exc)
    
    # Truncate very long error messages
    if len(error_msg) > 500:
        error_msg = error_msg[:500] + "..."
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {error_type}",
            "message": error_msg,
            "path": request.url.path,
        }
    )


# Public API
app.include_router(api_router, prefix="/api/v1")

# Internal API (agent tools)
app.include_router(internal_router, prefix="/internal/agent")

# WebSocket endpoint
app.include_router(ws_router)
