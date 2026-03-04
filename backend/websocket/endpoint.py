"""
WebSocket endpoint for real-time updates.

Docs contract: /ws?token=<TOKEN>&project_id=<UUID>&channels=agent_stream,messages,kanban,agents,activity,backend_logs,workflow,all
"""

from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.core.auth import verify_ws_token
from backend.core.ws_backend_log_stream import ws_backend_log_stream
from backend.websocket.events import create_backend_log_snapshot_event
from backend.websocket.manager import Channel, ws_manager
from backend.websocket.screen_stream import get_screen_stream_proxy
from backend.websocket.vnc_proxy import proxy_vnc

router = APIRouter()

_CHANNEL_MAP = {
    "agent_stream": Channel.AGENT_STREAM,
    "messages": Channel.MESSAGES,
    "kanban": Channel.KANBAN,
    "agents": Channel.AGENTS,
    "activity": Channel.ACTIVITY,
    "backend_logs": Channel.BACKEND_LOGS,
    "workflow": Channel.WORKFLOW,
    "all": Channel.ALL,
}


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    project_id: UUID = Query(..., description="Project ID to subscribe to"),
    channels: str = Query(
        "all",
        description="Comma-separated: agent_stream,messages,kanban,agents,activity,backend_logs,workflow,all",
    ),
):
    """
    WebSocket endpoint for real-time updates (docs contract).

    Channels: agent_stream (agent_text, agent_tool_call, agent_tool_result),
    messages (agent_message, system_message), kanban, agents, activity, workflow, all.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    channel_list = []
    for ch in channels.split(","):
        ch = ch.strip().lower()
        if ch in _CHANNEL_MAP:
            channel_list.append(_CHANNEL_MAP[ch])

    if not channel_list:
        channel_list.append(Channel.ALL)

    await ws_manager.connect(websocket, project_id, channel_list)
    if Channel.BACKEND_LOGS in channel_list or Channel.ALL in channel_list:
        items, latest_seq = ws_backend_log_stream.snapshot()
        snapshot_event = create_backend_log_snapshot_event(items, latest_seq)
        await websocket.send_json(snapshot_event.model_dump(mode="json"))

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "subscribe":
                channel = data.get("channel", "").strip().lower()
                if channel in _CHANNEL_MAP:
                    await ws_manager.subscribe(websocket, _CHANNEL_MAP[channel])
                    if _CHANNEL_MAP[channel] in {Channel.BACKEND_LOGS, Channel.ALL}:
                        items, latest_seq = ws_backend_log_stream.snapshot()
                        snapshot_event = create_backend_log_snapshot_event(items, latest_seq)
                        await websocket.send_json(snapshot_event.model_dump(mode="json"))
            elif data.get("type") == "unsubscribe":
                channel = data.get("channel", "").strip().lower()
                if channel in _CHANNEL_MAP:
                    await ws_manager.unsubscribe(websocket, _CHANNEL_MAP[channel])
            elif data.get("type") == "inspect_agent":
                agent_id = data.get("agent_id")
                if agent_id:
                    try:
                        await ws_manager.set_inspected_agent(websocket, UUID(str(agent_id)))
                    except ValueError:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid agent_id for inspect_agent"}
                        )
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


@router.websocket("/ws/screen")
async def screen_stream_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    sandbox_id: str = Query(..., description="Sandbox ID to stream"),
):
    """
    WebSocket endpoint for live screen streaming from a sandbox container.

    Transparently relays binary JPEG frames from the sandbox's /ws/screen
    endpoint to the frontend viewer.  The upstream connection is shared
    across multiple viewers of the same sandbox.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    proxy = get_screen_stream_proxy()
    await proxy.add_viewer(sandbox_id, websocket)
    try:
        while True:
            data = await websocket.receive()
            if data.get("type") == "websocket.disconnect":
                break
            # Handle ping/pong
            if "text" in data:
                import json
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except (json.JSONDecodeError, TypeError):
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await proxy.remove_viewer(sandbox_id, websocket)


@router.websocket("/ws/vnc")
async def vnc_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    sandbox_id: str = Query(..., description="Sandbox ID to connect to"),
):
    """
    WebSocket endpoint for interactive VNC remote desktop.

    Bidirectionally relays VNC/RFB protocol bytes between a frontend noVNC
    client and a sandbox container's /ws/vnc endpoint.  Unlike the MJPEG
    screen stream, each VNC session is stateful and dedicated to one viewer.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept(subprotocol="binary")
    await proxy_vnc(sandbox_id, websocket)
