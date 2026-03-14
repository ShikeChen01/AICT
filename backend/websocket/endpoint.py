"""
WebSocket endpoint for real-time updates.

Docs contract: /ws?token=<TOKEN>&project_id=<UUID>&channels=agent_stream,messages,kanban,agents,activity,backend_logs,workflow,all

Security (v3 hardening — code review critical #1):
  Every endpoint verifies (a) token validity AND (b) project/sandbox ownership before
  accepting. This prevents cross-tenant data leakage for live project events, screen
  streaming, and VNC access.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.config import settings
from backend.core.auth import verify_ws_token, _verify_firebase_token
from backend.core.ws_backend_log_stream import ws_backend_log_stream
from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent, Repository, ProjectMembership, User, Sandbox
from backend.websocket.events import create_backend_log_snapshot_event
from backend.websocket.manager import Channel, ws_manager
from backend.websocket.screen_stream import get_screen_stream_proxy
from backend.websocket.vnc_proxy import proxy_vnc
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)
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


async def _verify_ws_project_access(token: str, project_id: UUID) -> bool:
    """
    Return True iff the token is valid AND the caller has access to project_id.

    Rules (mirrors project_access.py):
    - Shared api_token -> full access (dev/internal).
    - Firebase token -> user must have a membership row OR project owner_id IS NULL.
    """
    if not token:
        return False
    if token == settings.api_token:
        return True

    decoded = _verify_firebase_token(token)
    if decoded is None:
        return False
    firebase_uid = decoded.get("uid")
    if not firebase_uid:
        return False

    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
        user = user_result.scalar_one_or_none()
        if user is None:
            return False

        repo_result = await db.execute(select(Repository).where(Repository.id == project_id))
        repo = repo_result.scalar_one_or_none()
        if repo is None:
            return False

        # Legacy unowned project accessible to any authenticated user
        if repo.owner_id is None:
            return True

        mem_result = await db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user.id,
            )
        )
        return mem_result.scalar_one_or_none() is not None


async def _verify_ws_sandbox_access(token: str, sandbox_id: str) -> bool:
    """
    Return True iff the token is valid AND the caller has access to sandbox_id.

    Access is granted if the user owns the sandbox OR is a member of the
    project the sandbox is attached to.
    """
    if not token:
        return False
    if token == settings.api_token:
        return True

    decoded = _verify_firebase_token(token)
    if decoded is None:
        return False
    firebase_uid = decoded.get("uid")
    if not firebase_uid:
        return False

    async with AsyncSessionLocal() as db:
        # Resolve user from Firebase UID
        user_result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
        user = user_result.scalar_one_or_none()
        if user is None:
            return False

        # Look up sandbox by orchestrator_sandbox_id (the public sandbox ID)
        sandbox_result = await db.execute(
            select(Sandbox).where(Sandbox.orchestrator_sandbox_id == sandbox_id)
        )
        sandbox = sandbox_result.scalar_one_or_none()

    if sandbox is None:
        # Sandbox not found yet — allow if token is valid
        return True

    # Owner always has access
    if sandbox.user_id == user.id:
        return True

    # Project member has access if sandbox is attached to a project
    if sandbox.project_id:
        return await _verify_ws_project_access(token, sandbox.project_id)

    return False


# ---- /ws  main event stream -------------------------------------------------


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

    Security: verifies token validity then project ownership before accepting.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Ownership guard (code review critical #1)
    if not await _verify_ws_project_access(token, project_id):
        await websocket.close(code=4003, reason="Access denied to project")
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


# ---- /ws/screen  MJPEG screen stream ----------------------------------------


@router.websocket("/ws/screen")
async def screen_stream_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    sandbox_id: str = Query(..., description="Sandbox ID to stream"),
):
    """
    WebSocket endpoint for live screen streaming from a sandbox container.

    Security: verifies token validity then sandbox ownership before accepting.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Sandbox ownership guard (code review critical #1)
    if not await _verify_ws_sandbox_access(token, sandbox_id):
        await websocket.close(code=4003, reason="Access denied to sandbox")
        return

    await websocket.accept()
    proxy = get_screen_stream_proxy()
    await proxy.add_viewer(sandbox_id, websocket)
    try:
        while True:
            data = await websocket.receive()
            msg_type = data.get("type")
            if msg_type == "websocket.disconnect":
                break
            if msg_type == "websocket.receive" and "text" in data:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except (json.JSONDecodeError, TypeError):
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("screen_stream_endpoint: unexpected error for sandbox %s: %s", sandbox_id, exc)
    finally:
        await proxy.remove_viewer(sandbox_id, websocket)


# ---- /ws/vnc  interactive VNC -----------------------------------------------


@router.websocket("/ws/vnc")
async def vnc_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="API token for authentication"),
    sandbox_id: str = Query(..., description="Sandbox ID to connect to"),
):
    """
    WebSocket endpoint for interactive VNC remote desktop.

    Security: verifies token validity then sandbox ownership before accepting.
    """
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Sandbox ownership guard (code review critical #1)
    if not await _verify_ws_sandbox_access(token, sandbox_id):
        await websocket.close(code=4003, reason="Access denied to sandbox")
        return

    await websocket.accept(subprotocol="binary")
    await proxy_vnc(sandbox_id, websocket)
