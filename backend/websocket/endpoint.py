"""
WebSocket endpoint for real-time updates.

Docs contract: /ws?token=<TOKEN>&project_id=<UUID>&channels=agent_stream,messages,kanban,agents,activity,workflow,all
"""

from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.core.auth import verify_ws_token
from backend.websocket.manager import Channel, ws_manager

router = APIRouter()

_CHANNEL_MAP = {
    "agent_stream": Channel.AGENT_STREAM,
    "messages": Channel.MESSAGES,
    "kanban": Channel.KANBAN,
    "agents": Channel.AGENTS,
    "activity": Channel.ACTIVITY,
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
        description="Comma-separated: agent_stream,messages,kanban,agents,activity,workflow,all",
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

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "subscribe":
                channel = data.get("channel", "").strip().lower()
                if channel in _CHANNEL_MAP:
                    await ws_manager.subscribe(websocket, _CHANNEL_MAP[channel])
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
