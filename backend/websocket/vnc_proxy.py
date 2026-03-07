"""
VNC WebSocket proxy — relays noVNC traffic from frontend to sandbox containers.

Architecture:
  Frontend (noVNC RFB client)  ←→  VncProxy (backend)  ←→  Sandbox container
                                                              (/ws/vnc endpoint)

Unlike the MJPEG screen stream, VNC connections are stateful and interactive
(one connection per user session).  No fan-out multiplexing — each frontend
WebSocket gets its own upstream connection to the sandbox.

Cloud Run notes:
  - Keepalive pings on the upstream (backend → sandbox) prevent idle-timeout
    disconnects.  Uvicorn's websockets layer auto-pings the frontend side.
  - The "binary" subprotocol is negotiated with the sandbox upstream.
  - Cloud Run request timeout must be >= 3600s for long-lived VNC sessions
    (configured in the deploy script via --timeout).
"""

from __future__ import annotations

import asyncio

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import get_sandbox_client

logger = get_logger(__name__)

# Keepalive ping interval (seconds) for the upstream connection to the sandbox.
# Cloud Run's overall request timeout is the hard limit; this ping prevents
# intermediary TCP proxies and the sandbox from dropping idle connections.
_UPSTREAM_PING_INTERVAL_S = 30


async def proxy_vnc(sandbox_id: str, viewer_ws: WebSocket) -> None:
    """
    Bidirectionally relay VNC/RFB protocol bytes between a frontend
    noVNC WebSocket and a sandbox container's /ws/vnc endpoint.
    """
    client = get_sandbox_client()
    conn = client._connections.get(sandbox_id)
    if not conn:
        # Backend may have restarted — try to re-register from pool manager
        from backend.services.sandbox_service import PoolManagerClient
        from backend.config import settings
        try:
            pool = PoolManagerClient()
            data = await pool.get_sandbox_by_id(sandbox_id)
            client.register(
                sandbox_id=sandbox_id,
                vm_host=settings.sandbox_vm_host,
                host_port=data["host_port"],
                auth_token=data["auth_token"],
            )
            conn = client._connections.get(sandbox_id)
        except Exception as exc:
            logger.warning("VNC proxy: sandbox %s not registered and re-registration failed: %s", sandbox_id, exc)
            await viewer_ws.close(code=4004, reason="Sandbox not registered")
            return
        if not conn:
            await viewer_ws.close(code=4004, reason="Sandbox not registered")
            return

    upstream_url = (
        conn.rest_base_url.replace("http://", "ws://")
        + f"/ws/vnc?token={conn.auth_token}"
    )
    logger.info(
        "VNC proxy opening upstream to sandbox %s (%s)",
        sandbox_id,
        conn.rest_base_url,
    )

    try:
        async with websockets.connect(
            upstream_url,
            open_timeout=10,
            max_size=2**22,  # 4 MB — VNC frames can be large
            subprotocols=[websockets.Subprotocol("binary")],
            # Keepalive pings on the upstream WS (backend → sandbox).
            ping_interval=_UPSTREAM_PING_INTERVAL_S,
            ping_timeout=10,
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
                except WebSocketDisconnect:
                    logger.debug("VNC proxy: frontend disconnected (sandbox %s)", sandbox_id)
                except Exception as exc:
                    logger.debug("VNC proxy frontend_to_sandbox error (sandbox %s): %s", sandbox_id, exc)

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
                except WebSocketDisconnect:
                    logger.debug("VNC proxy: frontend gone during relay (sandbox %s)", sandbox_id)
                except Exception as exc:
                    logger.debug("VNC proxy sandbox_to_frontend error (sandbox %s): %s", sandbox_id, exc)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(frontend_to_sandbox()),
                    asyncio.create_task(sandbox_to_frontend()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except (ConnectionRefusedError, OSError) as exc:
        logger.warning("VNC proxy connection refused for sandbox %s: %s", sandbox_id, exc)
        try:
            await viewer_ws.close(code=1011, reason=f"VNC upstream refused: {exc}")
        except Exception:
            pass
    except websockets.exceptions.InvalidStatusCode as exc:
        logger.warning("VNC proxy bad status for sandbox %s: %s", sandbox_id, exc)
        try:
            await viewer_ws.close(code=1011, reason=f"VNC upstream HTTP error: {exc}")
        except Exception:
            pass
    except websockets.exceptions.WebSocketException as exc:
        logger.warning("VNC proxy WS error for sandbox %s: %s", sandbox_id, exc)
        try:
            await viewer_ws.close(code=1011, reason=f"VNC upstream error: {exc}")
        except Exception:
            pass
    except Exception as exc:
        logger.exception("VNC proxy unexpected error for sandbox %s: %s", sandbox_id, exc)
        try:
            await viewer_ws.close(code=1011, reason="Internal proxy error")
        except Exception:
            pass
    finally:
        logger.info("VNC proxy session ended for sandbox %s", sandbox_id)
