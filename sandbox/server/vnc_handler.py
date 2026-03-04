"""
VNC WebSocket bridge — connects a WebSocket client to the local x11vnc
VNC server (TCP 5900), enabling noVNC browser clients to interact with
the sandbox desktop.

This is essentially what websockify does, but integrated into our
existing FastAPI server so we don't need a second exposed port.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect


async def handle_vnc_ws(ws: WebSocket) -> None:
    """
    Bridge a WebSocket connection to the local VNC server on TCP 5900.

    Bidirectionally relays binary data between the WebSocket (noVNC client)
    and the TCP socket (x11vnc VNC server).
    """
    await ws.accept(subprotocol="binary")

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 5900)
    except (ConnectionRefusedError, OSError) as exc:
        await ws.close(code=1011, reason=f"VNC server unavailable: {exc}")
        return

    async def ws_to_tcp() -> None:
        """Forward WebSocket messages to the VNC TCP socket."""
        try:
            while True:
                data = await ws.receive()
                if data.get("type") == "websocket.disconnect":
                    break
                payload = data.get("bytes") or data.get("text")
                if payload:
                    if isinstance(payload, str):
                        payload = payload.encode("latin-1")
                    writer.write(payload)
                    await writer.drain()
        except (WebSocketDisconnect, Exception):
            pass

    async def tcp_to_ws() -> None:
        """Forward VNC TCP data to the WebSocket client."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await ws.send_bytes(data)
        except (WebSocketDisconnect, Exception):
            pass

    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(ws_to_tcp()), asyncio.create_task(tcp_to_ws())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
