"""
Sandboxes REST API — user-owned sandbox management endpoints.

v3.1: Auth model is ownership-based (sandbox.user_id == current_user.id).
Project members can also access sandboxes attached to their project.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import Sandbox, SandboxConfig, SandboxSnapshot, User
from backend.db.session import get_db
from backend.services.sandbox_service import (
    CapacityExhaustedError,
    SandboxAlreadyAssigned,
    SandboxLimitReached,
    SandboxOwnershipError,
    SandboxService,
)
from backend.services.tier_service import TierService
from backend.core.exceptions import TierLimitError

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def _get_sandbox_service() -> SandboxService:
    return SandboxService()


# ── Request/Response models ───────────────────────────────────────────────


class SandboxResponse(BaseModel):
    id: str
    user_id: str
    project_id: str | None
    agent_id: str | None
    agent_name: str | None = None
    sandbox_config_id: str | None = None
    name: str | None = None
    description: str | None = None
    orchestrator_sandbox_id: str
    unit_type: str = "headless"  # v4: "headless" | "desktop"
    status: str
    host: str | None
    port: int
    created_at: str | None
    assigned_at: str | None


class CreateSandboxRequest(BaseModel):
    config_id: UUID | None = None
    name: str | None = Field(None, max_length=100)
    description: str | None = None
    project_id: UUID | None = None
    requires_desktop: bool = False  # v4: request a desktop VM instead of headless container


class UpdateSandboxRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = None
    config_id: UUID | None = None
    project_id: UUID | None = None


class AssignRequest(BaseModel):
    agent_id: UUID


class TransferRequest(BaseModel):
    new_owner_id: UUID


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


class SnapshotCreateRequest(BaseModel):
    label: str | None = None


class SnapshotRestoreRequest(BaseModel):
    snapshot_id: UUID


# ── Helpers ───────────────────────────────────────────────────────────────


def _sandbox_to_response(sb: Sandbox) -> dict:
    """Convert Sandbox ORM to response dict."""
    return {
        "id": str(sb.id),
        "user_id": str(sb.user_id),
        "project_id": str(sb.project_id) if sb.project_id else None,
        "agent_id": str(sb.agent_id) if sb.agent_id else None,
        "agent_name": (
            sb.agent.display_name if sb.agent else None
        ),
        "sandbox_config_id": (
            str(sb.sandbox_config_id) if sb.sandbox_config_id else None
        ),
        "name": sb.name,
        "description": sb.description,
        "orchestrator_sandbox_id": sb.orchestrator_sandbox_id,
        "unit_type": getattr(sb, "unit_type", "headless"),
        "status": sb.status,
        "host": sb.host,
        "port": sb.port or 8080,
        "created_at": sb.created_at.isoformat() if sb.created_at else None,
        "assigned_at": sb.assigned_at.isoformat() if sb.assigned_at else None,
    }


def _snapshot_to_response(snap: SandboxSnapshot) -> dict:
    return {
        "id": str(snap.id),
        "sandbox_id": str(snap.sandbox_id),
        "label": snap.label,
        "k8s_snapshot_name": snap.k8s_snapshot_name,
        "os_image": snap.os_image,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


def create_sandbox_jwt(
    sandbox_id: str, user_id: str, ttl_seconds: int | None = None
) -> str:
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
    """Load sandbox and verify the user has access.

    Access is granted if the user owns the sandbox OR is a member of the
    project the sandbox is attached to.
    """
    result = await db.execute(
        select(Sandbox)
        .where(Sandbox.id == sandbox_id)
        .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
    )
    sandbox = result.scalar_one_or_none()
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Owner always has access
    if sandbox.user_id == user_id:
        return sandbox

    # Project member has read access
    if sandbox.project_id:
        try:
            await require_project_access(db, sandbox.project_id, user_id)
            return sandbox
        except Exception:
            pass

    raise HTTPException(status_code=403, detail="No access to this sandbox")


async def _require_sandbox_owner(
    db: AsyncSession,
    sandbox_id: UUID,
    user_id: UUID,
) -> Sandbox:
    """Load sandbox and verify the user is the owner (stricter than access)."""
    sandbox = await _require_sandbox_access(db, sandbox_id, user_id)
    if sandbox.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Only the sandbox owner can perform this action"
        )
    return sandbox


# ── CRUD Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=SandboxResponse, status_code=201)
async def create_sandbox(
    body: CreateSandboxRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user-owned sandbox."""
    # Tier enforcement: check sandbox hour limits
    tier_svc = TierService(db)
    try:
        unit_type = "desktop" if body.requires_desktop else "headless"
        await tier_svc.check_can_start_sandbox(current_user, unit_type)
    except TierLimitError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_limit",
                "message": str(exc),
                "current_tier": exc.current_tier,
                "upgrade_url": exc.upgrade_url,
            },
        ) from exc

    svc = _get_sandbox_service()
    try:
        sandbox = await svc.create_sandbox(
            db,
            current_user.id,
            config_id=body.config_id,
            name=body.name,
            description=body.description,
            project_id=body.project_id,
            requires_desktop=body.requires_desktop,
        )
        await db.commit()
    except SandboxLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Sandbox limit reached ({exc.current_count}/{exc.limit})",
        ) from exc
    except CapacityExhaustedError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "capacity_exhausted",
                "message": "No capacity available to create this sandbox",
                **exc.detail,
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.get("", response_model=list[SandboxResponse])
async def list_sandboxes(
    project_id: UUID | None = Query(None, description="Filter by project"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's sandboxes, optionally filtered by project.

    If project_id is given, also includes sandboxes owned by other users
    that are attached to the project (if the user has project access).
    """
    svc = _get_sandbox_service()

    if project_id:
        # Verify project access, then return all project sandboxes
        await require_project_access(db, project_id, current_user.id)
        sandboxes = await svc.list_for_project(db, project_id)
    else:
        sandboxes = await svc.list_for_user(db, current_user.id)

    # Best-effort sync with pool manager's live unit status
    await svc.sync_pool_status(db, sandboxes)
    await db.commit()

    return [_sandbox_to_response(sb) for sb in sandboxes]


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get sandbox details."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)
    return _sandbox_to_response(sandbox)


@router.patch("/{sandbox_id}", response_model=SandboxResponse)
async def update_sandbox(
    sandbox_id: UUID,
    body: UpdateSandboxRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update sandbox properties. Owner only."""
    sandbox = await _require_sandbox_owner(db, sandbox_id, current_user.id)

    if body.name is not None:
        sandbox.name = body.name
    if body.description is not None:
        sandbox.description = body.description
    if body.config_id is not None:
        sandbox.sandbox_config_id = body.config_id
    if body.project_id is not None:
        sandbox.project_id = body.project_id

    await db.commit()
    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.delete("/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently destroy a sandbox. Owner only."""
    sandbox = await _require_sandbox_owner(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    await svc.destroy(db, sandbox)
    await db.commit()
    return {"ok": True, "sandbox_id": str(sandbox_id), "message": "Sandbox destroyed"}


# ── Agent assignment ──────────────────────────────────────────────────────


@router.post("/{sandbox_id}/assign", response_model=SandboxResponse)
async def assign_sandbox(
    sandbox_id: UUID,
    body: AssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a sandbox to an agent. Owner only."""
    svc = _get_sandbox_service()
    try:
        sandbox = await svc.assign_to_agent(
            db, sandbox_id, body.agent_id, user_id=current_user.id
        )
        await db.commit()
    except SandboxOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SandboxAlreadyAssigned as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.post("/{sandbox_id}/unassign", response_model=SandboxResponse)
async def unassign_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detach sandbox from its agent. Owner only."""
    svc = _get_sandbox_service()
    try:
        sandbox = await svc.unassign_from_agent(
            db, sandbox_id, user_id=current_user.id
        )
        await db.commit()
    except SandboxOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.post("/{sandbox_id}/transfer", response_model=SandboxResponse)
async def transfer_sandbox(
    sandbox_id: UUID,
    body: TransferRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transfer sandbox ownership to another user. Owner only."""
    svc = _get_sandbox_service()
    try:
        sandbox = await svc.transfer_ownership(
            db, sandbox_id, current_user.id, body.new_owner_id
        )
        await db.commit()
    except SandboxOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


# ── Config & operations ───────────────────────────────────────────────────


@router.post("/{sandbox_id}/apply-config")
async def apply_config(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the sandbox config's setup script on the container."""
    sandbox = await _require_sandbox_owner(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    result = await svc.apply_config(db, sandbox)
    if result is None:
        return {"ok": True, "skipped": True, "message": "No config or setup script"}
    return result


@router.post("/{sandbox_id}/restart")
async def restart_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restart sandbox container (keeps volume).

    If the container is gone on the orchestrator, re-provisions it with the
    same config so the user gets their desktop back.
    """
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    try:
        result = await svc.restart(db, sandbox)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    action = result.get("action", "restarted")
    msg = (
        "Sandbox restarted"
        if action == "restarted"
        else "Sandbox was unreachable and has been re-provisioned"
    )
    return {"ok": True, "sandbox_id": str(sandbox_id), "action": action, "message": msg}


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
    )


@router.get("/{sandbox_id}/health")
async def check_sandbox_health(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a sandbox is actually reachable.

    Pings the sandbox container directly. If unreachable, updates
    the DB status to ``unreachable`` so the frontend can show it.
    """
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    try:
        await svc.sandbox_health(sandbox)
        sandbox.last_health_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        sandbox.status = sandbox.status if sandbox.status != "unreachable" else "ready"
        await db.commit()
        return {"ok": True, "sandbox_id": str(sandbox_id), "status": "healthy"}
    except Exception:
        sandbox.status = "unreachable"
        await db.commit()
        return {"ok": False, "sandbox_id": str(sandbox_id), "status": "unreachable"}


# ── Snapshots ─────────────────────────────────────────────────────────────


@router.post("/{sandbox_id}/snapshot", response_model=SnapshotResponse)
async def create_snapshot(
    sandbox_id: UUID,
    body: SnapshotCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a VolumeSnapshot of a sandbox."""
    sandbox = await _require_sandbox_access(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    snap = await svc.snapshot(db, sandbox, body.label or "")
    await db.commit()
    return _snapshot_to_response(snap)


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
    await db.commit()
    return {"ok": True, "sandbox_id": str(sandbox_id), "message": "Snapshot restored"}


@router.get("/{sandbox_id}/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all snapshots for a sandbox."""
    await _require_sandbox_access(db, sandbox_id, current_user.id)
    result = await db.execute(
        select(SandboxSnapshot).where(SandboxSnapshot.sandbox_id == sandbox_id)
    )
    return [_snapshot_to_response(snap) for snap in result.scalars().all()]


# ── Images catalog ────────────────────────────────────────────────────────


@router.get("/images")
async def list_sandbox_images(
    current_user: User = Depends(get_current_user),
):
    """List available OS images for sandbox creation."""
    svc = _get_sandbox_service()
    try:
        return await svc.list_images()
    except Exception:
        return [
            {
                "slug": "ubuntu-22.04",
                "display_name": "Ubuntu 22.04 LTS",
                "os_family": "linux",
                "default": True,
                "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}},
            },
        ]


# ── v4: Promote / Demote / Capacity ────────────────────────────────────────


@router.post("/{sandbox_id}/promote", response_model=SandboxResponse)
async def promote_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote a headless sandbox to desktop (Docker → QEMU sub-VM).

    Preserves working directory via file migration. Requires available
    desktop capacity in the Grand-VM budget.
    """
    sandbox = await _require_sandbox_owner(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    try:
        sandbox = await svc.promote_to_desktop(db, sandbox)
        await db.commit()
    except CapacityExhaustedError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "capacity_exhausted",
                "message": "No desktop capacity available for promotion",
                **exc.detail,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.post("/{sandbox_id}/demote", response_model=SandboxResponse)
async def demote_sandbox(
    sandbox_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Demote a desktop sandbox to headless (QEMU sub-VM → Docker container).

    Preserves working directory. Frees desktop resources back to the budget.
    """
    sandbox = await _require_sandbox_owner(db, sandbox_id, current_user.id)
    svc = _get_sandbox_service()
    try:
        sandbox = await svc.demote_to_headless(db, sandbox)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.refresh(sandbox, ["agent", "config"])
    return _sandbox_to_response(sandbox)


@router.get("/capacity")
async def get_capacity_status(
    current_user: User = Depends(get_current_user),
):
    """Get current Grand-VM capacity budget snapshot.

    Returns CPU/RAM/disk usage, headless/desktop counts, and whether
    new units of each type can be provisioned.
    """
    svc = _get_sandbox_service()
    try:
        return await svc.capacity_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
