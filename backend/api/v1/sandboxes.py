"""
Sandboxes REST API — user-facing sandbox management endpoints.

Allows users to manage sandboxes keyed by sandbox_id (not agent_id).
Supports claiming from warm pool, releasing, snapshotting, and direct connection.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Agent, Sandbox, SandboxConfig, SandboxSnapshot, User
from backend.db.session import get_db
from backend.config import settings
from backend.services.sandbox_service import SandboxService

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def _get_sandbox_service() -> SandboxService:
    return SandboxService()


# ── Response models ───────────────────────────────────────────────────────

class SandboxResponse(BaseModel):
    id: str
    project_id: str
    agent_id: str | None
    agent_name: str | None = None
    agent_role: str | None = None
    sandbox_config_id: str | None = None
    orchestrator_sandbox_id: str
    status: str
    host: str | None
    port: int
    created_at: str | None
    assigned_at: str | None


class ConnectionInfo(BaseModel):
    host: str
    port: int
    token: str
    vnc_path: str = "/ws/vnc"
    screen_path: str = "/ws/screen"


class SnapshotResponse(BaseModel):
    id: str
    sandbox_id: str
    label: str | None
    k8s_snapshot_name: str
    os_image: str
    created_at: str | None


class ClaimRequest(BaseModel):
    agent_id: UUID


class SnapshotCreateRequest(BaseModel):
    label: str | None = None


class SnapshotRestoreRequest(BaseModel):
    snapshot_id: UUID


# ── Helper functions ──────────────────────────────────────────────────────

def _sandbox_to_response(sb: Sandbox) -> dict:
    """Convert Sandbox ORM to SandboxResponse dict."""
    return {
        "id": str(sb.id),
        "project_id": str(sb.project_id),
        "agent_id": str(sb.agent_id) if sb.agent_id else None,
        "agent_name": sb.agent.display_name or sb.agent.role if sb.agent else None,
        "agent_role": sb.agent.role if sb.agent else None,
        "sandbox_config_id": str(sb.sandbox_config_id) if sb.sandbox_config_id else None,
        "orchestrator_sandbox_id": sb.orchestrator_sandbox_id,
        "status": sb.status,
        "host": sb.host,
        "port": sb.port or 8080,
        "created_at": sb.created_at.isoformat() if sb.created_at else None,
        "assigned_at": sb.assigned_at.isoformat() if sb.assigned_at else None,
    }


def _snapshot_to_response(snap: SandboxSnapshot) -> dict:
    """Convert SandboxSnapshot ORM to SnapshotResponse dict."""
    return {
        "id": str(snap.id),
        "sandbox_id": str(snap.sandbox_id),
        "label": snap.label,
        "k8s_snapshot_name": snap.k8s_snapshot_name,
        "os_image": snap.os_image,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


def create_sandbox_jwt(sandbox_id: str, user_id: str, ttl_seconds: int | None = None) -> str:
    """Generate a JWT for direct sandbox access."""
    if ttl_seconds is None:
        ttl_seconds = settings.sandbox_jwt_ttl_seconds or 3600
    payload = {
        "sandbox_id": sandbox_id,
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        "iat": datetime.now(timezone.utc),
    }
    secret = settings.sandbox_jwt_secret or "change-me"
    return jwt.encode(payload, secret, algorithm="HS256")


async def _require_sandbox_access(
    db: AsyncSession,
    sandbox_id: UUID,
    user_id: UUID,
) -> Sandbox:
    """Load a sandbox and verify project access."""
    result = await db.execute(
        select(Sandbox)
        .where(Sandbox.id == sandbox_id)
        .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
    )
    sandbox = result.scalar_one_or_none()
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    await require_project_access(db, sandbox.project_id, user_id)
    return sandbox


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[SandboxResponse])
async def list_sandboxes(
    project_id: UUID = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sandboxes for a project."""
    await require_project_access(db, project_id, current_user.id)

    result = await db.execute(
        select(Sandbox)
        .where(Sandbox.project_id == project_id)
        .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
    )
    sandboxes = result.scalars().all()

    return [_sandbox_to_response(sb) for sb in sandboxes]


@router.post("", response_model=SandboxResponse)
async def claim_sandbox(
    body: ClaimRequest,
    project_id: UUID = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a sandbox from the warm pool for an agent.

    If the agent already has a sandbox, returns the existing one.
    """
    await require_project_access(db, project_id, current_user.id)

    # Fetch the agent with sandbox relationship pre-loaded
    result = await db.execute(
        select(Agent)
        .where(Agent.id == body.agent_id)
        .options(selectinload(Agent.sandbox))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.project_id != project_id:
        raise HTTPException(status_code=403, detail="Agent not in this project")

    svc = _get_sandbox_service()
    try:
        sandbox = await svc.claim(db, agent)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start sandbox: {type(exc).__name__}: {exc}",
        ) from exc

    await db.commit()

    # Ensure the agent relationship is loaded for the response serializer
    await db.refresh(sandbox, ["agent"])

    return _sandbox_to_response(sandbox)


@router.post("/{sandbox_id}/release")
async def release_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a sandbox to the warm pool."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    svc = _get_sandbox_service()
    await svc.release(db, sandbox)
    # Note: release() already clears the relationship via sandbox.agent_id = None

    return {"ok": True, "sandbox_id": str(sandbox_id), "status": "released"}


@router.post("/{sandbox_id}/restart")
async def restart_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restart a sandbox container (keeps volume and installed apps)."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    svc = _get_sandbox_service()
    await svc.restart(db, sandbox)

    return {"ok": True, "sandbox_id": str(sandbox_id), "message": "Sandbox restarted"}


@router.delete("/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently destroy a sandbox and its volume."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    svc = _get_sandbox_service()
    await svc.destroy(db, sandbox)
    # Note: destroy() handles cleanup including agent relationship

    return {"ok": True, "sandbox_id": str(sandbox_id), "message": "Sandbox destroyed"}


@router.patch("/{sandbox_id}")
async def update_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update sandbox properties."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    await db.commit()
    return _sandbox_to_response(sandbox)


@router.post("/{sandbox_id}/apply-config")
async def apply_config(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the sandbox config setup script."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    if not sandbox.sandbox_config_id:
        return {"ok": True, "skipped": True, "message": "No config assigned"}

    result = await db.execute(
        select(SandboxConfig).where(SandboxConfig.id == sandbox.sandbox_config_id)
    )
    config = result.scalar_one_or_none()
    if not config or not config.setup_script:
        return {"ok": True, "skipped": True, "message": "Config has no setup script"}

    svc = _get_sandbox_service()
    result = await svc._orchestrator.run_setup(
        sandbox.orchestrator_sandbox_id,
        config.setup_script,
    )
    return result


@router.get("/{sandbox_id}/connect", response_model=ConnectionInfo)
async def get_connection_info(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get connection info and JWT token for direct frontend access."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    if not sandbox.host:
        raise HTTPException(status_code=503, detail="Sandbox host not available")

    token = create_sandbox_jwt(str(sandbox.id), str(current_user.id))

    return ConnectionInfo(
        host=sandbox.host,
        port=sandbox.port or 8080,
        token=token,
        vnc_path="/ws/vnc",
        screen_path="/ws/screen",
    )


@router.post("/{sandbox_id}/snapshot", response_model=SnapshotResponse)
async def create_snapshot(
    sandbox_id: UUID,
    body: SnapshotCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a snapshot of a sandbox."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    svc = _get_sandbox_service()
    snapshot = await svc.snapshot(db, sandbox, body.label or "")

    return _snapshot_to_response(snapshot)


@router.post("/{sandbox_id}/restore")
async def restore_snapshot(
    sandbox_id: UUID,
    body: SnapshotRestoreRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore a sandbox from a snapshot."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    svc = _get_sandbox_service()
    await svc.restore(db, sandbox, str(body.snapshot_id))

    return {"ok": True, "sandbox_id": str(sandbox_id), "message": "Snapshot restored"}


@router.get("/{sandbox_id}/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all snapshots for a sandbox."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)

    result = await db.execute(
        select(SandboxSnapshot).where(SandboxSnapshot.sandbox_id == sandbox_id)
    )
    snapshots = result.scalars().all()

    return [_snapshot_to_response(snap) for snap in snapshots]


@router.get("/images")
async def list_sandbox_images(
    current_user: User = Depends(get_current_user),
):
    """List available OS images for sandbox creation."""
    svc = _get_sandbox_service()
    try:
        return await svc.list_images()
    except Exception:
        # Fallback to minimal static catalog
        return [
            {
                "slug": "ubuntu-22.04",
                "display_name": "Ubuntu 22.04 LTS",
                "os_family": "linux",
                "default": True,
                "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}},
            },
        ]
