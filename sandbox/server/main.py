"""Sandbox server — FastAPI app running inside each container."""

from __future__ import annotations

import asyncio
import subprocess
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import require_token, validate_ws_token
from config import DISPLAY, PORT
from display_handler import router as display_router
from recording_handler import router as record_router
from shell_handler import handle_shell_ws
from stream_handler import ScreenStreamer

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

    app.state.screen_streamer = ScreenStreamer()

    yield  # app is running

    await app.state.screen_streamer.shutdown()


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


class ShellExecuteRequest(BaseModel):
    command: str
    timeout: int = 120


@app.post("/shell/execute", dependencies=[Depends(require_token)])
async def shell_execute(body: ShellExecuteRequest) -> JSONResponse:
    """Execute a shell command and return stdout + exit code (REST alternative to WS shell)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            body.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"DISPLAY": DISPLAY, "HOME": "/root", "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=body.timeout,
        )
        stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
        return JSONResponse({
            "stdout": stdout,
            "exit_code": proc.returncode,
        })
    except asyncio.TimeoutError:
        proc.kill()
        return JSONResponse({"stdout": "Command timed out", "exit_code": -1}, status_code=408)
    except Exception as exc:
        return JSONResponse({"stdout": str(exc), "exit_code": -1}, status_code=500)


@app.websocket("/ws/shell")
async def shell_ws(ws: WebSocket, token: str = Depends(validate_ws_token)):
    await handle_shell_ws(ws, token)


@app.websocket("/ws/screen")
async def screen_ws(ws: WebSocket, token: str = Depends(validate_ws_token)):
    """Stream MJPEG frames from Xvfb to the client."""
    await ws.accept()
    streamer: ScreenStreamer = app.state.screen_streamer
    await streamer.add_client(ws)
    try:
        while True:
            data = await ws.receive()
            if data.get("type") == "websocket.disconnect":
                break
            # Handle text control messages (quality/fps)
            if "text" in data:
                await streamer.handle_client_message(data["text"])
            elif "bytes" in data:
                await streamer.handle_client_message(data["bytes"])
    except Exception:
        pass
    finally:
        await streamer.remove_client(ws)
