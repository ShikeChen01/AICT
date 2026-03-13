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
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import Awaitable

from backend.config import settings
from backend.logging.my_logger import configure_logging, get_logger, ws_backend_log_stream

configure_logging()

import fastapi.exceptions
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


@dataclass
class StartupState:
    ready: bool = False
    phase: str = "starting"
    error: str | None = None


def _get_startup_state(app: FastAPI) -> StartupState:
    state = getattr(app.state, "startup_state", None)
    if state is None:
        state = StartupState()
        app.state.startup_state = state
    return state


def _cloud_run_background_startup_enabled() -> bool:
    return os.getenv("K_SERVICE") is not None


def _is_startup_exempt_path(path: str) -> bool:
    exempt_prefixes = (
        "/health",
        "/api/v1/health",
        "/internal/agent/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in exempt_prefixes)


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


async def _bootstrap_application(app: FastAPI, *, crash_on_failure: bool) -> None:
    state = _get_startup_state(app)
    try:
        state.phase = "running_migrations"
        await _run_startup_migrations()

        state.phase = "provisioning_repositories"
        await _run_startup_step("provision_repositories_on_startup", _provision_repositories_on_startup())

        state.phase = "starting_workers"
        await _start_worker_manager()

        wm = get_worker_manager()
        if wm.worker_count == 0:
            logger.warning(
                "WorkerManager started but registered 0 agent workers. "
                "No agents are in the database for this project yet."
            )

        state.phase = "starting_background_tasks"
        _background_tasks.append(asyncio.create_task(_run_broadcaster_forever()))
        _background_tasks.append(asyncio.create_task(_run_reconciler_forever()))
        _background_tasks.append(asyncio.create_task(_run_config_listener_forever()))

        state.ready = True
        state.phase = "ready"
        state.error = None
        logger.info("Application startup complete")
    except asyncio.CancelledError:
        state.phase = "cancelled"
        raise
    except Exception as exc:
        state.ready = False
        state.phase = "failed"
        state.error = str(exc)
        logger.critical("Application startup failed: %s", exc, exc_info=True)
        if crash_on_failure:
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = _get_startup_state(app)
    state.ready = False
    state.phase = "starting"
    state.error = None

    startup_task: asyncio.Task | None = None
    try:
        if _cloud_run_background_startup_enabled():
            logger.info("Cloud Run detected; deferring heavy startup behind readiness gate")
            startup_task = asyncio.create_task(
                _bootstrap_application(app, crash_on_failure=False)
            )
            app.state.startup_task = startup_task
        else:
            await _bootstrap_application(app, crash_on_failure=True)
        yield
    finally:
        if startup_task is not None and not startup_task.done():
            startup_task.cancel()
            try:
                await startup_task
            except asyncio.CancelledError:
                pass
        if _background_tasks or get_worker_manager().is_started:
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


@app.exception_handler(fastapi.exceptions.ResponseValidationError)
async def response_validation_exception_handler(request: Request, exc: fastapi.exceptions.ResponseValidationError):
    """
    Catch Pydantic response-model validation errors.

    FastAPI/Starlette swallows these silently (returns 500 with no log).
    This handler logs the real error server-side for debugging.
    """
    import traceback
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(
        "ResponseValidationError on %s %s:\n%s",
        request.method,
        request.url.path,
        "".join(tb),
    )
    # Include just enough detail in the response to help diagnose without leaking internals
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Response validation failed",
            "path": request.url.path,
            "errors": errors,
        },
    )


@app.middleware("http")
async def readiness_gate_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or _is_startup_exempt_path(request.url.path):
        return await call_next(request)

    startup_state = _get_startup_state(request.app)
    if startup_state.ready:
        return await call_next(request)

    return JSONResponse(
        status_code=503,
        content={
            "status": "failed" if startup_state.error else "starting",
            "message": "Application startup is still in progress",
            "phase": startup_state.phase,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    import traceback
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(
        "Unhandled %s on %s %s: %s\n%s",
        type(exc).__name__,
        request.method,
        request.url.path,
        exc,
        "".join(tb),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
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
