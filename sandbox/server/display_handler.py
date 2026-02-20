"""Display control: screenshots, mouse, keyboard via xdotool + ffmpeg."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from auth import require_token
from config import DISPLAY, SCREENSHOT_QUALITY, SCREEN_HEIGHT, SCREEN_WIDTH

router = APIRouter(dependencies=[Depends(require_token)])

SCREENSHOT_PATH = Path("/tmp/sandbox_screenshot.jpg")


async def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a subprocess asynchronously."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"DISPLAY": DISPLAY, "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail=f"Command timed out: {cmd[0]}")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


# ── Screenshot ───────────────────────────────────────────────────────────────


@router.get("/screenshot")
async def screenshot() -> FileResponse:
    """Capture a single frame from Xvfb and return as JPEG."""
    result = await _run([
        "ffmpeg", "-y",
        "-f", "x11grab",
        "-video_size", f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}",
        "-i", DISPLAY,
        "-vframes", "1",
        "-q:v", str(SCREENSHOT_QUALITY),
        str(SCREENSHOT_PATH),
    ])
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg failed: {result.stderr.decode()[:500]}",
        )
    return FileResponse(
        str(SCREENSHOT_PATH),
        media_type="image/jpeg",
        filename="screenshot.jpg",
    )


# ── Mouse ────────────────────────────────────────────────────────────────────


class MouseMoveRequest(BaseModel):
    x: int
    y: int


@router.post("/mouse/move")
async def mouse_move(body: MouseMoveRequest) -> JSONResponse:
    """Move the mouse cursor to (x, y)."""
    result = await _run(["xdotool", "mousemove", str(body.x), str(body.y)])
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.decode()[:300])
    return JSONResponse({"ok": True, "x": body.x, "y": body.y})


@router.get("/mouse/location")
async def mouse_location() -> JSONResponse:
    """Return current mouse cursor position."""
    result = await _run(["xdotool", "getmouselocation"])
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.decode()[:300])
    # Output format: "x:123 y:456 screen:0 window:789"
    parts = {}
    for token in result.stdout.decode().split():
        if ":" in token:
            k, v = token.split(":", 1)
            parts[k] = v
    return JSONResponse({"x": int(parts.get("x", 0)), "y": int(parts.get("y", 0))})


# ── Keyboard ─────────────────────────────────────────────────────────────────


class KeyboardRequest(BaseModel):
    keys: str | None = None    # For xdotool key (e.g. "ctrl+c", "Return")
    text: str | None = None    # For xdotool type (raw text)


@router.post("/keyboard")
async def keyboard(body: KeyboardRequest) -> JSONResponse:
    """Press keys or type text using xdotool."""
    if body.keys:
        result = await _run(["xdotool", "key", body.keys])
    elif body.text:
        result = await _run(["xdotool", "type", "--clearmodifiers", body.text])
    else:
        raise HTTPException(status_code=400, detail="Provide 'keys' or 'text'")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.decode()[:300])
    return JSONResponse({"ok": True})
