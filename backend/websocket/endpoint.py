"""
WebSocket endpoint for real-time updates.

Clients connect via: /ws?token=<API_TOKEN>&project_id=<UUID>&channels=chat,kanban
"""

from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.core.auth import verify_ws_token
from backend.websocket.manager import Channel, ws_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    project_id: UUID = Query(..., description="Project ID to subscribe to"),
    channels: str = Query("all", description="Comma-separated channels: chat,kanban,all"),
):
    """
    WebSocket endpoint for real-time updates.

    Query Parameters:
    - token: API token for authentication
    - project_id: Project ID to subscribe to events for
    - channels: Comma-separated list of channels (chat, kanban, all)

    Events sent:
    - chat_message: When GM responds
    - gm_status: When GM becomes busy/available
    - task_created: When a new task is created
    - task_update: When a task is updated
    - agent_status: When an agent's status changes
    """
    # Authenticate
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Parse channels
    channel_list = []
    for ch in channels.split(","):
        ch = ch.strip().lower()
        if ch == "chat":
            channel_list.append(Channel.CHAT)
        elif ch == "kanban":
            channel_list.append(Channel.KANBAN)
        elif ch == "all":
            channel_list.append(Channel.ALL)

    if not channel_list:
        channel_list.append(Channel.ALL)

    # Connect and manage lifecycle
    await ws_manager.connect(websocket, project_id, channel_list)

    try:
        while True:
            # Listen for client messages (ping/pong, subscribe/unsubscribe)
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "subscribe":
                channel = data.get("channel", "").lower()
                if channel == "chat":
                    await ws_manager.subscribe(websocket, Channel.CHAT)
                elif channel == "kanban":
                    await ws_manager.subscribe(websocket, Channel.KANBAN)

            elif data.get("type") == "unsubscribe":
                channel = data.get("channel", "").lower()
                if channel == "chat":
                    await ws_manager.unsubscribe(websocket, Channel.CHAT)
                elif channel == "kanban":
                    await ws_manager.unsubscribe(websocket, Channel.KANBAN)

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
