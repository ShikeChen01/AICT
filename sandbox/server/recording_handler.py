"""Screen recording via ffmpeg x11grab."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from auth import require_token
from config import DISPLAY, RECORD_FPS, RECORD_OUTPUT, SCREEN_HEIGHT, SCREEN_WIDTH

router = APIRouter(dependencies=[Depends(require_token)])

_recording_proc: asyncio.subprocess.Process | None = None


@router.post("/record/start")
async def record_start() -> JSONResponse:
    """Start screen recording (2 fps, h264 ultrafast)."""
    global _recording_proc

    if _recording_proc is not None and _recording_proc.returncode is None:
        return JSONResponse({"ok": True, "status": "already_recording"})

    # Remove stale output file
    try:
        os.remove(RECORD_OUTPUT)
    except FileNotFoundError:
        pass

    _recording_proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "x11grab",
        "-framerate", str(RECORD_FPS),
        "-video_size", f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}",
        "-i", DISPLAY,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        RECORD_OUTPUT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            "DISPLAY": DISPLAY,
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        },
    )
    return JSONResponse({"ok": True, "status": "started", "output": RECORD_OUTPUT})


@router.post("/record/stop")
async def record_stop() -> FileResponse:
    """Stop recording and return the video file."""
    global _recording_proc

    if _recording_proc is None or _recording_proc.returncode is not None:
        raise HTTPException(status_code=400, detail="No active recording")

    try:
        _recording_proc.send_signal(signal.SIGINT)
        await asyncio.wait_for(_recording_proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        _recording_proc.kill()
        await _recording_proc.wait()
    finally:
        _recording_proc = None

    output_path = Path(RECORD_OUTPUT)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="Recording file missing or empty")

    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename="recording.mp4",
    )
