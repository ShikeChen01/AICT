"""
Screen stream proxy — relays MJPEG frames from sandbox containers to frontend viewers.

Architecture:
  Frontend viewer(s)  ←→  ScreenStreamProxy (backend)  ←→  Sandbox container
                                                             (/ws/screen endpoint)

Key design:
  - One upstream WS connection per actively-viewed sandbox (shared across viewers)
  - Binary JPEG frames are relayed transparently (no re-encoding)
  - Upstream connection is torn down when the last viewer disconnects
  - Subscribe/unsubscribe semantics via add_viewer/remove_viewer
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import get_sandbox_client

logger = get_logger(__name__)


@dataclass
class _UpstreamState:
    """Tracks one upstream connection to a sandbox's /ws/screen endpoint."""
    sandbox_id: str
    viewers: set[WebSocket] = field(default_factory=set)
    task: asyncio.Task | None = None
    upstream_ws: object | None = None  # websockets.WebSocketClientProtocol


class ScreenStreamProxy:
    """
    Multiplexes screen streams from sandbox containers to frontend viewers.

    Thread-safe via asyncio.  One instance per backend process.
    """

    def __init__(self) -> None:
        self._streams: dict[str, _UpstreamState] = {}
        self._lock = asyncio.Lock()

    async def add_viewer(self, sandbox_id: str, viewer_ws: WebSocket) -> None:
        """Subscribe a frontend viewer to a sandbox's screen stream."""
        async with self._lock:
            state = self._streams.get(sandbox_id)
            if state is None:
                state = _UpstreamState(sandbox_id=sandbox_id)
                self._streams[sandbox_id] = state
            state.viewers.add(viewer_ws)
            if state.task is None or state.task.done():
                state.task = asyncio.create_task(self._relay_loop(sandbox_id))
                logger.info("Started screen stream relay for sandbox %s", sandbox_id)

    async def remove_viewer(self, sandbox_id: str, viewer_ws: WebSocket) -> None:
        """Unsubscribe a frontend viewer from a sandbox's screen stream."""
        async with self._lock:
            state = self._streams.get(sandbox_id)
            if state is None:
                return
            state.viewers.discard(viewer_ws)
            if not state.viewers:
                if state.task and not state.task.done():
                    state.task.cancel()
                del self._streams[sandbox_id]
                logger.info("Stopped screen stream relay for sandbox %s (no viewers)", sandbox_id)

    async def _relay_loop(self, sandbox_id: str) -> None:
        """Connect to sandbox /ws/screen and relay binary frames to all viewers."""
        import websockets

        client = get_sandbox_client()
        conn = client._connections.get(sandbox_id)
        if not conn:
            logger.warning("Cannot relay screen stream: sandbox %s not registered", sandbox_id)
            return

        ws_url = (
            conn.rest_base_url.replace("http://", "ws://")
            + f"/ws/screen?token={conn.auth_token}"
        )

        try:
            async with websockets.connect(ws_url, open_timeout=10) as upstream:
                logger.info("Connected to upstream screen stream for sandbox %s", sandbox_id)
                async with self._lock:
                    state = self._streams.get(sandbox_id)
                    if state:
                        state.upstream_ws = upstream

                async for message in upstream:
                    if isinstance(message, bytes):
                        await self._fan_out(sandbox_id, message)
                    # Text messages are ignored (control plane not relayed)

        except asyncio.CancelledError:
            logger.info("Screen stream relay cancelled for sandbox %s", sandbox_id)
        except Exception as exc:
            logger.warning("Screen stream relay error for sandbox %s: %s", sandbox_id, exc)
        finally:
            async with self._lock:
                state = self._streams.get(sandbox_id)
                if state:
                    state.upstream_ws = None

    async def _fan_out(self, sandbox_id: str, frame: bytes) -> None:
        """Send a JPEG frame to all viewers of a sandbox."""
        async with self._lock:
            state = self._streams.get(sandbox_id)
            if not state:
                return
            dead: list[WebSocket] = []
            for ws in state.viewers:
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_bytes(frame)
                    else:
                        dead.append(ws)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                state.viewers.discard(ws)

    async def shutdown(self) -> None:
        """Clean shutdown — cancel all relay tasks."""
        async with self._lock:
            for state in self._streams.values():
                if state.task and not state.task.done():
                    state.task.cancel()
            self._streams.clear()


# Process-level singleton
_screen_stream_proxy: ScreenStreamProxy | None = None


def get_screen_stream_proxy() -> ScreenStreamProxy:
    global _screen_stream_proxy
    if _screen_stream_proxy is None:
        _screen_stream_proxy = ScreenStreamProxy()
    return _screen_stream_proxy
