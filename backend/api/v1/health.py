"""
Health check endpoint.

GET /health  — returns 200 with basic status info.
Used by GKE liveness/readiness probes and load balancers.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.workers.worker_manager import get_worker_manager

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=True)
async def health_check(request: Request) -> JSONResponse:
    """
    Liveness / readiness probe.

    Returns 200 when the application is up and WorkerManager has started.
    Returns 503 if the WorkerManager has not yet started (startup still in progress).
    """
    startup_state = getattr(request.app.state, "startup_state", None)
    wm = get_worker_manager()
    if startup_state is not None and not startup_state.ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed" if startup_state.error else "starting",
                "message": "Application startup is still in progress",
                "phase": startup_state.phase,
            },
        )

    if not wm.is_started:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "message": "WorkerManager not yet ready"},
        )
    status = wm.get_status()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "worker_count": status["worker_count"],
        },
    )
