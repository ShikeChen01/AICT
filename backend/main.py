"""
AICT Backend — FastAPI application entry point.

v3 security hardening:
- CORS: allow_origins read from ALLOWED_ORIGINS env var (default localhost only)
- Global exception handler: does NOT leak exception type or message to clients
- Migration failure: hard-fail (raises) instead of soft-fail so the container
  restarts rather than serving a broken schema (code review high #1)
"""

import asyncio
import os
from contextlib import asynccontextmanager
from collections.abc import Awaitable

from backend.config import settings
from backend.logging.my_logger import configure_logging, get_logger, ws_backend_log_stream

configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.v1.router import api_router
from backend.api.v1.test_login import router as test_login_router
from backend.api_internal.router import internal_router
from backend.core.error_handlers import aict_exception_handler
from backend.core.exceptions import AICTException
from backend.db.migration_runner import run_startup_migrations
from backend.db.session import AsyncSessionLocal
from backend.workers.worker_manager import get_worker_manager
from backend.services.repo_provisioning import RepoProvisioningService
from backend.websocket.endpoint import router as ws_router

logger = get_logger(__name__)

# Track background tasks
_background_tasks: list[asyncio.Task] = []


async def _run_startup_step(name: str, step: Awaitable[None]) -> None:
    """
    Run an optional startup step with timeout and soft-fail behavior.
    Use only for truly non-critical steps (repo provisioning).
    Migrations are NOT run through this path — they use the hard-fail path.
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
        logger.warning("Repository provisioning skipped: %s", exc)


_WORKER_STARTUP_RETRIES = 3
_WORKER_STARTUP_RETRY_DELAY_S = 5


async def _start_worker_manager() -> None:
    """
    Start WorkerManager with retry logic. Raises on all failures so that
    Cloud Run restarts the container rather than serving a broken backend.

    Intentionally NOT wrapped in _run_startup_step — agent workers are critical.
    """
    from backend.workers.worker_manager import reset_worker_manager

    last_exc: Exception | None = None

    for attempt in range(1, _WORKER_STARTUP_RETRIES + 1):
        manager = get_worker_manager()
        try:
            await asyncio.wait_for(manager.start(), timeout=120)
            status = manager.get_status()
            logger.info(
                "WorkerManager started (attempt %d/%d): worker_count=%d agent_ids=%s",
                attempt,
                _WORKER_STARTUP_RETRIES,
                status["worker_count"],
                status["agent_ids"],
            )
            return
        except TimeoutError as exc:
            last_exc = exc
            logger.error(
                "WorkerManager startup timed out (attempt %d/%d, timeout=120s)",
                attempt,
                _WORKER_STARTUP_RETRIES,
            )
        except Exception as exc:
            last_exc = exc
            logger.exception(
                "WorkerManager startup failed (attempt %d/%d): %s",
                attempt,
                _WORKER_STARTUP_RETRIES,
                exc,
            )

        if attempt < _WORKER_STARTUP_RETRIES:
            logger.info("Retrying WorkerManager startup in %ds...", _WORKER_STARTUP_RETRY_DELAY_S)
            try:
                await manager.stop()
            except Exception:
                pass
            reset_worker_manager()
            await asyncio.sleep(_WORKER_STARTUP_RETRY_DELAY_S)

    raise RuntimeError(
        f"WorkerManager failed to start after {_WORKER_STARTUP_RETRIES} attempts. "
        f"Last error: {last_exc}"
    )


async def _run_reconciler_forever() -> None:
    from backend.workers.reconciler import run_reconciler_forever
    while True:
        try:
            await run_reconciler_forever()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Reconciler stopped unexpectedly (%s), restarting in 5s", exc)
            await asyncio.sleep(5)


async def _run_config_listener_forever() -> None:
    from backend.agents.config_listener import ConfigListener, _asyncpg_dsn
    wm = get_worker_manager()
    dsn = _asyncpg_dsn(settings.database_url)
    listener = ConfigListener(dsn=dsn, worker_manager=wm)
    try:
        await listener.run_forever()
    except asyncio.CancelledError:
        await listener.stop()
        raise
    except Exception as exc:
        logger.error("ConfigListener exited unexpectedly: %s", exc)
        raise


async def _run_broadcaster_forever() -> None:
    ws_backend_log_stream.bind_loop(asyncio.get_running_loop())
    while True:
        try:
            await ws_backend_log_stream.run_broadcaster()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Backend log broadcaster stopped unexpectedly (%s), restarting in 2s", exc)
            await asyncio.sleep(2)


async def _run_startup_migrations() -> None:
    """
    Run database migrations.

    v3 change: migration failure is a HARD FAIL — we raise so the container
    restarts rather than booting against an unmigrated schema (code review high #1).
    The original soft-fail masked schema drift bugs as runtime errors.
    """
    if not settings.auto_run_migrations_on_startup:
        logger.info("Auto migrations disabled (AUTO_RUN_MIGRATIONS_ON_STARTUP=false)")
        return
    try:
        await asyncio.to_thread(run_startup_migrations)
        logger.info("Database migrations are up to date")
    except Exception as exc:
        logger.critical(
            "Database migration FAILED — aborting startup to prevent schema drift: %s", exc
        )
        raise RuntimeError(f"Startup aborted: migration failed: {exc}") from exc


async def _stop_background_tasks() -> None:
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
    # Migrations: hard-fail so startup aborts on schema drift
    await _run_startup_migrations()

    # Repo provisioning: still soft-fail (non-critical)
    await _run_startup_step("provision_repositories_on_startup", _provision_repositories_on_startup())

    # Workers: hard-fail (already raises after retries)
    await _start_worker_manager()

    wm = get_worker_manager()
    if wm.worker_count == 0:
        logger.warning(
            "WorkerManager started but registered 0 agent workers. "
            "No agents are in the database for this project yet."
        )
    _background_tasks.append(asyncio.create_task(_run_broadcaster_forever()))
    _background_tasks.append(asyncio.create_task(_run_reconciler_forever()))
    _background_tasks.append(asyncio.create_task(_run_config_listener_forever()))
    yield
    await _stop_background_tasks()


app = FastAPI(title="AICT Backend", version="0.3.0", lifespan=lifespan)

# ---- CORS -------------------------------------------------------------------
# v3 hardening: restrict origins to configured list (code review medium #3).
# Set ALLOWED_ORIGINS env var to a comma-separated list for production.
# Development default remains localhost variants.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if _raw_origins.strip():
    _allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    _allowed_origins = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Exception handlers -----------------------------------------------------

app.add_exception_handler(AICTException, aict_exception_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.

    v3 hardening: does NOT include exception type or message in the response
    body (code review medium #2). Full details still logged server-side.
    """
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred. Please try again or contact support.",
            "path": request.url.path,
        },
    )


# ---- Routers ----------------------------------------------------------------

# Test login (dev only — path is obfuscated to reduce accidental exposure)
app.include_router(test_login_router)

# Public API
app.include_router(api_router, prefix="/api/v1")

# Internal API (agent tools)
app.include_router(internal_router, prefix="/internal/agent")

# WebSocket
app.include_router(ws_router)

# Health / metrics (v3)
from backend.api.v1 import health, metrics as metrics_router  # noqa: E402
app.include_router(health.router)
app.include_router(metrics_router.router)
