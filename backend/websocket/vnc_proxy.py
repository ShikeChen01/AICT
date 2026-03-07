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


def _short_reason(msg: str) -> str:
    """Keep WS close reason under 123 bytes so proxies don't strip it."""
    return (msg[:120] + "…") if len(msg) > 123 else msg


async def _safe_close_viewer(ws: WebSocket, code: int, reason: str) -> None:
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close(code=code, reason=_short_reason(reason))
    except Exception:
        pass


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
            vm_host = settings.sandbox_vm_internal_host or settings.sandbox_vm_host
            client.register(
                sandbox_id=sandbox_id,
                vm_host=vm_host,
                host_port=data["host_port"],
                auth_token=data["auth_token"],
            )
            conn = client._connections.get(sandbox_id)
        except Exception as exc:
            logger.warning("VNC proxy: sandbox %s not registered and re-registration failed: %s", sandbox_id, exc)
            await _safe_close_viewer(viewer_ws, 4004, "Sandbox not registered")
            return
        if not conn:
            await _safe_close_viewer(viewer_ws, 4004, "Sandbox not registered")
            return

    from backend.config import settings

    upstream_url = (
        conn.rest_base_url.replace("http://", "ws://")
        + f"/ws/vnc?token={conn.auth_token}"
    )
    logger.info(
        "VNC proxy opening upstream to sandbox %s (%s)",
        sandbox_id,
        conn.rest_base_url,
    )

    # Use short timeouts so we can send a proper close frame before proxies drop the connection.
    _connect_timeout = 8
    _open_timeout = 6

    upstream = None
    last_exc: Exception | None = None
    try:
        upstream = await asyncio.wait_for(
            websockets.connect(
                upstream_url,
                open_timeout=_open_timeout,
                max_size=2**22,
                subprotocols=[websockets.Subprotocol("binary")],
                ping_interval=_UPSTREAM_PING_INTERVAL_S,
                ping_timeout=10,
            ).__aenter__(),
            timeout=_connect_timeout,
        )
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as exc:
        last_exc = exc
        upstream = None
    except (websockets.exceptions.InvalidStatusCode, websockets.exceptions.WebSocketException) as exc:
        last_exc = exc
        upstream = None

    # Fallback: if internal host failed and we have external host, try once
    if upstream is None and last_exc is not None and settings.sandbox_vm_internal_host and settings.sandbox_vm_host:
        if conn.rest_base_url.startswith(f"http://{settings.sandbox_vm_internal_host}:"):
            try:
                port = conn.rest_base_url.rstrip("/").split(":")[-1]
                client.register(sandbox_id=sandbox_id, vm_host=settings.sandbox_vm_host, host_port=int(port), auth_token=conn.auth_token)
                conn = client._connections.get(sandbox_id)
                if conn:
                    upstream_url = conn.rest_base_url.replace("http://", "ws://") + f"/ws/vnc?token={conn.auth_token}"
                    logger.info("VNC proxy retry upstream via external host %s", conn.rest_base_url)
                    upstream = await asyncio.wait_for(
                        websockets.connect(upstream_url, open_timeout=_open_timeout, max_size=2**22, subprotocols=[websockets.Subprotocol("binary")], ping_interval=_UPSTREAM_PING_INTERVAL_S, ping_timeout=10,
                        ).__aenter__(),
                        timeout=_connect_timeout,
                    )
            except Exception as retry_exc:
                logger.warning("VNC proxy retry via external host failed: %s", retry_exc)
                last_exc = retry_exc
                upstream = None

    if upstream is None:
        reason = "VNC upstream unreachable"
        if last_exc is not None:
            reason = _short_reason(f"Upstream: {type(last_exc).__name__}: {last_exc}")
        logger.warning("VNC proxy cannot reach sandbox %s: %s", sandbox_id, last_exc)
        await _safe_close_viewer(viewer_ws, 1011, reason)
        return

    try:
        async with upstream:
            logger.info("VNC proxy connected to sandbox %s", sandbox_id)

            async def frontend_to_sandbox() -> None:
                """Forward binary frames from noVNC client to sandbox VNC server."""
                try:
                    while True:
                        data = await viewer_ws.receive()
                        msg_type = data.get("type")
                        if msg_type == "websocket.disconnect":
                            break
                        if msg_type != "websocket.receive":
                            continue
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
        await _safe_close_viewer(viewer_ws, 1011, f"Upstream refused: {exc}")
    except websockets.exceptions.InvalidStatusCode as exc:
        logger.warning("VNC proxy bad status for sandbox %s: %s", sandbox_id, exc)
        await _safe_close_viewer(viewer_ws, 1011, f"Upstream HTTP error: {exc}")
    except websockets.exceptions.WebSocketException as exc:
        logger.warning("VNC proxy WS error for sandbox %s: %s", sandbox_id, exc)
        await _safe_close_viewer(viewer_ws, 1011, f"Upstream error: {exc}")
    except Exception as exc:
        logger.exception("VNC proxy unexpected error for sandbox %s: %s", sandbox_id, exc)
        await _safe_close_viewer(viewer_ws, 1011, "Internal proxy error")
    finally:
        logger.info("VNC proxy session ended for sandbox %s", sandbox_id)
