"""
VNC WebSocket proxy — relays noVNC traffic from frontend to sandbox containers.

Architecture:
  Frontend (noVNC RFB client)  ←→  VncProxy (backend)  ←→  Sandbox container
                                                              (/ws/vnc endpoint)

Unlike the MJPEG screen stream, VNC connections are stateful and interactive
(one connection per user session).  No fan-out multiplexing — each frontend
WebSocket gets its own upstream connection to the sandbox.
"""

from __future__ import annotations

import asyncio

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import get_sandbox_client

logger = get_logger(__name__)


async def proxy_vnc(sandbox_id: str, viewer_ws: WebSocket) -> None:
    """
    Bidirectionally relay VNC/RFB protocol bytes between a frontend
    noVNC WebSocket and a sandbox container's /ws/vnc endpoint.
    """
    client = get_sandbox_client()
    conn = client._connections.get(sandbox_id)
    if not conn:
        logger.warning("VNC proxy: sandbox %s not registered", sandbox_id)
        await viewer_ws.close(code=4004, reason="Sandbox not registered")
        return

    upstream_url = (
        conn.rest_base_url.replace("http://", "ws://")
        + f"/ws/vnc?token={conn.auth_token}"
    )

    try:
        async with websockets.connect(
            upstream_url,
            open_timeout=10,
            max_size=2**22,  # 4 MB — VNC frames can be large
        ) as upstream:
            logger.info("VNC proxy connected to sandbox %s", sandbox_id)

            async def frontend_to_sandbox() -> None:
                """Forward binary frames from noVNC client to sandbox VNC server."""
                try:
                    while True:
                        data = await viewer_ws.receive()
                        if data.get("type") == "websocket.disconnect":
                            break
                        payload = data.get("bytes") or data.get("text")
                        if payload:
                            if isinstance(payload, str):
                                await upstream.send(payload.encode("latin-1"))
                            else:
                                await upstream.send(payload)
                except (WebSocketDisconnect, Exception):
                    pass

            async def sandbox_to_frontend() -> None:
                """Forward VNC server responses to the noVNC client."""
                try:
                    async for message in upstream:
                        if viewer_ws.client_state != WebSocketState.CONNECTED:
                            break
                        if isinstance(message, bytes):
                            await viewer_ws.send_bytes(message)
                        else:
                            await viewer_ws.send_text(message)
                except (WebSocketDisconnect, Exception):
                    pass

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(frontend_to_sandbox()),
                    asyncio.create_task(sandbox_to_frontend()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except (ConnectionRefusedError, OSError, websockets.exceptions.WebSocketException) as exc:
        logger.warning("VNC proxy failed for sandbox %s: %s", sandbox_id, exc)
        try:
            await viewer_ws.close(code=1011, reason=f"VNC upstream error: {exc}")
        except Exception:
            pass
    finally:
        logger.info("VNC proxy disconnected from sandbox %s", sandbox_id)
