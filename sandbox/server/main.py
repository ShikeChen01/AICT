"""Sandbox server — FastAPI app running inside each container."""

from __future__ import annotations

import asyncio
import subprocess
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import JSONResponse

from auth import require_token, validate_ws_token
from config import DISPLAY, PORT
from display_handler import router as display_router
from recording_handler import router as record_router
from shell_handler import handle_shell_ws

_start_time = time.time()


def _xvfb_running() -> bool:
    """Check if Xvfb is already serving the configured display."""
    try:
        result = subprocess.run(
            ["xdpyinfo", "-display", DISPLAY],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for Xvfb to be ready (started by entrypoint.sh before uvicorn)
    for _ in range(20):
        if _xvfb_running():
            break
        await asyncio.sleep(0.5)
    else:
        # Non-fatal — log and continue; Xvfb may still be starting
        print(f"[sandbox-server] WARNING: Xvfb not detected on {DISPLAY}")

    yield  # app is running

    # Nothing to clean up — container teardown handles everything


app = FastAPI(title="Sandbox Server", lifespan=lifespan)

app.include_router(display_router)
app.include_router(record_router)


@app.get("/health", dependencies=[Depends(require_token)])
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "display": DISPLAY,
    })


@app.websocket("/ws/shell")
async def shell_ws(ws: WebSocket, token: str = Depends(validate_ws_token)):
    await handle_shell_ws(ws, token)
