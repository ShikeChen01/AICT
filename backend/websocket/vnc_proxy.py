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


async def _resolve_sandbox_connection(sandbox_id: str) -> tuple[str | None, int, str | None]:
    """Look up sandbox host/port/auth_token, applying dev tunnel if needed."""
    from backend.db.session import AsyncSessionLocal
    from backend.db.models import Sandbox
    from sqlalchemy import select

    host = port = auth_token = None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Sandbox).where(Sandbox.orchestrator_sandbox_id == sandbox_id)
            )
            sandbox = result.scalar_one_or_none()
            if sandbox:
                host = sandbox.host
                port = sandbox.port
                auth_token = sandbox.auth_token
    except Exception as exc:
        logger.warning("Sandbox %s DB lookup failed: %s", sandbox_id, exc)

    if not host or not auth_token:
        from backend.services.sandbox_service import OrchestratorClient
        try:
            orch = OrchestratorClient()
            data = await orch.get_sandbox_by_id(sandbox_id)
            host = data.get("host")
            port = data.get("port", data.get("host_port", 8080))
            auth_token = data.get("auth_token")
        except Exception as exc:
            logger.warning("Sandbox %s orchestrator lookup failed: %s", sandbox_id, exc)

    if not host or not auth_token:
        return (None, port or 8080, None)

    # In dev mode, ClusterIPs are unreachable — tunnel through kubectl port-forward
    import os
    if os.getenv("ENV", "").lower() == "development":
        from backend.services.sandbox_tunnel import get_tunnel_manager
        try:
            tunnel_host, tunnel_port = await get_tunnel_manager().get_host_port(sandbox_id, port or 8080)
            logger.info("Using dev tunnel for sandbox %s: %s:%d", sandbox_id, tunnel_host, tunnel_port)
            return (tunnel_host, tunnel_port, auth_token)
        except Exception as exc:
            logger.warning("Dev tunnel failed for sandbox %s, falling back to direct: %s: %s", sandbox_id, type(exc).__name__, exc)

    return (host, port or 8080, auth_token)


async def proxy_vnc(sandbox_id: str, viewer_ws: WebSocket) -> None:
    """
    Bidirectionally relay VNC/RFB protocol bytes between a frontend
    noVNC WebSocket and a sandbox container's /ws/vnc endpoint.
    """
    from backend.config import settings

    host, port, auth_token = await _resolve_sandbox_connection(sandbox_id)

    if not host or not auth_token:
        await _safe_close_viewer(viewer_ws, 4004, "Sandbox not registered")
        return

    rest_base_url = f"http://{host}:{port}"
    upstream_url = f"ws://{host}:{port}/ws/vnc?token={auth_token}"
    logger.info(
        "VNC proxy opening upstream to sandbox %s (%s)",
        sandbox_id,
        rest_base_url,
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
        if rest_base_url.startswith(f"http://{settings.sandbox_vm_internal_host}:"):
            try:
                ext_upstream_url = f"ws://{settings.sandbox_vm_host}:{port}/ws/vnc?token={auth_token}"
                logger.info("VNC proxy retry upstream via external host %s:%s", settings.sandbox_vm_host, port)
                upstream = await asyncio.wait_for(
                    websockets.connect(ext_upstream_url, open_timeout=_open_timeout, max_size=2**22, subprotocols=[websockets.Subprotocol("binary")], ping_interval=_UPSTREAM_PING_INTERVAL_S, ping_timeout=10,
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

    # NOTE: `upstream` was obtained via manual `__aenter__()` so it is
    # already an open WebSocketClientProtocol — do NOT wrap it in another
    # ``async with`` (it doesn't support the context manager protocol).
    try:
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
        await _safe_close_viewer(
            viewer_ws, 1011,
            _short_reason(f"Proxy error: {type(exc).__name__}: {exc}"),
        )
    finally:
        # Close the upstream connection (since we bypassed the context manager)
        try:
            await upstream.close()
        except Exception:
            pass
        logger.info("VNC proxy session ended for sandbox %s", sandbox_id)
