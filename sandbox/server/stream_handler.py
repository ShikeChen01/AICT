"""Screen streaming — MJPEG frames over WebSocket with fan-out to N clients.

Manages a single ffmpeg x11grab subprocess that captures JPEG frames to stdout.
The capture process starts on the first client connection and stops when the
last client disconnects (zero-viewer = zero CPU).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from config import DISPLAY, SCREEN_HEIGHT, SCREEN_WIDTH, STREAM_FPS, STREAM_QUALITY

# JPEG markers
_SOI = b"\xff\xd8"  # Start Of Image
_EOI = b"\xff\xd9"  # End Of Image


class ScreenStreamer:
    """Fan-out MJPEG streaming from Xvfb to connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._proc: asyncio.subprocess.Process | None = None
        self._capture_task: asyncio.Task[None] | None = None
        self._fps: int = STREAM_FPS
        self._quality: int = STREAM_QUALITY

    async def add_client(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)
            if self._proc is None:
                self._start_capture()

    async def remove_client(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
            if not self._clients:
                await self._stop_capture()

    async def handle_client_message(self, data: bytes | str) -> None:
        """Handle control messages from a client (quality/fps adjustments)."""
        try:
            if isinstance(data, bytes):
                data = data.decode()
            msg: dict[str, Any] = json.loads(data)
            msg_type = msg.get("type")
            value = msg.get("value")
            if msg_type == "quality" and isinstance(value, int) and 1 <= value <= 31:
                self._quality = value
                await self._restart_capture()
            elif msg_type == "fps" and isinstance(value, int) and 1 <= value <= 30:
                self._fps = value
                await self._restart_capture()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def _start_capture(self) -> None:
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def _stop_capture(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            self._proc = None
        if self._capture_task is not None:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
            self._capture_task = None

    async def _restart_capture(self) -> None:
        """Restart ffmpeg with updated quality/fps settings."""
        async with self._lock:
            if self._clients:
                await self._stop_capture()
                self._start_capture()

    async def _capture_loop(self) -> None:
        """Spawn ffmpeg and fan-out JPEG frames to all connected clients."""
        cmd = [
            "ffmpeg",
            "-f", "x11grab",
            "-framerate", str(self._fps),
            "-video_size", f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}",
            "-i", DISPLAY,
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", str(self._quality),
            "pipe:1",
        ]
        env = {
            "DISPLAY": DISPLAY,
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        }

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            assert self._proc.stdout is not None

            buf = b""
            while True:
                chunk = await self._proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk

                # Extract complete JPEG frames from the buffer
                while True:
                    soi_idx = buf.find(_SOI)
                    if soi_idx == -1:
                        buf = b""
                        break
                    eoi_idx = buf.find(_EOI, soi_idx + 2)
                    if eoi_idx == -1:
                        # Incomplete frame — trim junk before SOI, wait for more data
                        buf = buf[soi_idx:]
                        break
                    # Complete frame: SOI through EOI (inclusive of 2-byte EOI marker)
                    frame = buf[soi_idx : eoi_idx + 2]
                    buf = buf[eoi_idx + 2 :]
                    await self._broadcast_frame(frame)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[stream_handler] capture loop error: {exc}")
        finally:
            if self._proc is not None:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
                self._proc = None

    async def _broadcast_frame(self, frame: bytes) -> None:
        """Send a JPEG frame to all connected clients."""
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._clients:
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_bytes(frame)
                    else:
                        dead.append(ws)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)
            if not self._clients:
                await self._stop_capture()

    async def shutdown(self) -> None:
        """Clean shutdown — stop capture and close all clients."""
        async with self._lock:
            await self._stop_capture()
            self._clients.clear()
