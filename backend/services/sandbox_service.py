"""
Sandbox Service — user-owned sandbox lifecycle management backed by the
warm pool orchestrator with DB persistence.

v3.1 refactoring: sandboxes are user-owned resources. Two clean paths:
  Path 1: User-managed lifecycle (create, assign, unassign, update, transfer, clone, destroy)
  Path 2: Sandbox manipulation (shell, VNC, screenshots, recording)

The old agent-triggered claim() flow is preserved as a deprecated compat shim.
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.core.exceptions import SandboxNotFoundError
from backend.db.models import Agent, Sandbox, SandboxConfig, SandboxSnapshot
from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import SandboxClient, ShellResult

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

DEFAULT_OS_IMAGE = "ubuntu-22.04"
DEFAULT_MAX_SANDBOXES_PER_USER = 100


# ── Sentinel for optional kwargs ──────────────────────────────────────────

class _SentinelType:
    """Distinguishes 'not provided' from None in optional kwargs."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<NOT_PROVIDED>"

    def __bool__(self) -> bool:
        return False


_SENTINEL = _SentinelType()


# ── Exceptions ────────────────────────────────────────────────────────────

class SandboxLimitReached(Exception):
    """User has reached their sandbox quota."""

    def __init__(self, current_count: int, limit: int = DEFAULT_MAX_SANDBOXES_PER_USER):
        self.current_count = current_count
        self.limit = limit
        super().__init__(f"Sandbox limit reached: {current_count}/{limit}")


class SandboxAlreadyAssigned(Exception):
    """Sandbox is already assigned to an agent."""

    def __init__(self, sandbox_id: UUID, agent_id: UUID):
        super().__init__(
            f"Sandbox {sandbox_id} is already assigned to agent {agent_id}"
        )


class SandboxOwnershipError(Exception):
    """User does not own this sandbox."""

    def __init__(self, sandbox_id: UUID, user_id: UUID):
        super().__init__(f"User {user_id} does not own sandbox {sandbox_id}")


# ── API response dataclass (backward compat) ─────────────────────────────

@dataclass(slots=True)
class SandboxMetadata:
    """Backward-compatible metadata returned by legacy lifecycle methods."""

    sandbox_id: str
    agent_id: str
    persistent: bool
    status: str
    host_port: int = 0
    auth_token: str = ""
    created: bool = False
    restarted: bool = False
    previous_sandbox_id: str | None = None
    message: str = ""


# ── Orchestrator Client ───────────────────────────────────────────────────

class OrchestratorClient:
    """Async REST client for the sandbox orchestrator (GKE or legacy VM).

    This class is a thin HTTP wrapper — it knows nothing about DB models
    or business rules.
    """

    def __init__(self) -> None:
        if settings.sandbox_orchestrator_host:
            host = settings.sandbox_orchestrator_host
            port = settings.sandbox_orchestrator_port
            token = settings.sandbox_orchestrator_token
        else:
            host = settings.sandbox_vm_internal_host or settings.sandbox_vm_host
            port = settings.sandbox_vm_pool_port
            token = settings.sandbox_vm_master_token

        self._base = f"http://{host}:{port}/api"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._is_gke = bool(settings.sandbox_orchestrator_host)

    # ── Warm pool ─────────────────────────────────────────────────────

    async def provision_warm(self, os_image: str = DEFAULT_OS_IMAGE) -> dict:
        """Create an idle sandbox and return to warm pool."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base}/pool/provision",
                json={"os_image": os_image},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def claim(
        self,
        sandbox_id: str,
        *,
        agent_id: str | None = None,
        project_id: str | None = None,
        setup_script: str | None = None,
    ) -> dict:
        """Claim an idle sandbox from the pool."""
        body: dict = {}
        if agent_id:
            body["agent_id"] = agent_id
        if project_id:
            body["project_id"] = project_id
        if setup_script:
            body["setup_script"] = setup_script
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/claim",
                json=body,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def release(self, sandbox_id: str) -> dict:
        """Return a sandbox to the warm pool."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/release",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def pool_metrics(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/pool/metrics",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Snapshot operations ───────────────────────────────────────────

    async def create_snapshot(self, sandbox_id: str, label: str = "") -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/snapshot",
                json={"label": label},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def restore_snapshot(self, sandbox_id: str, snapshot_name: str) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/restore",
                json={"snapshot_name": snapshot_name},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_snapshots(self, sandbox_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/{sandbox_id}/snapshots",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Session endpoints ─────────────────────────────────────────────

    async def session_start(
        self,
        *,
        persistent: bool = False,
        setup_script: str | None = None,
        os_image: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        """Ask the orchestrator to provision a new sandbox."""
        body: dict = {"persistent": persistent}
        if agent_id:
            body["agent_id"] = agent_id
        if setup_script:
            body["setup_script"] = setup_script
        if os_image:
            body["os_image"] = os_image
        if project_id:
            body["project_id"] = project_id
        read_timeout = 300.0 if setup_script else 120.0
        timeout = httpx.Timeout(read_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base}/sandbox/session/start",
                json=body,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def session_end(self, agent_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/session/end",
                json={"agent_id": agent_id},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._base}/health", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    async def list_sandboxes(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/list", headers=self._headers
            )
            resp.raise_for_status()
            return resp.json()

    async def destroy(self, sandbox_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{self._base}/sandbox/{sandbox_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def restart_sandbox(self, sandbox_id: str) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/restart",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def set_persistent(self, sandbox_id: str, persistent: bool) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/persistent",
                json={"persistent": persistent},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def run_setup(self, sandbox_id: str, setup_script: str) -> dict:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/run-setup",
                json={"setup_script": setup_script},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_sandbox_by_id(self, sandbox_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/{sandbox_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_images(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/images",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()


# ── Helpers ───────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_config(config: SandboxConfig | None) -> tuple[str, str | None, bool]:
    """Extract (os_image, setup_script, persistent) from a SandboxConfig."""
    if not config:
        return DEFAULT_OS_IMAGE, None, False
    return (
        config.os_image or DEFAULT_OS_IMAGE,
        config.setup_script or None,
        bool(config.persistent),
    )


# ── Sandbox Service ───────────────────────────────────────────────────────

class SandboxService:
    """User-owned sandbox lifecycle management.

    Two clean paths:
      1. User-managed lifecycle: create → configure → assign → unassign → destroy
      2. Sandbox manipulation: shell, VNC, screenshots, recording (keyed by sandbox)

    Plus a deprecated compat shim for the old agent-triggered claim flow.
    """

    def __init__(self) -> None:
        self._orchestrator = OrchestratorClient()
        self._client = SandboxClient()

    def _vm_configured(self) -> bool:
        return bool(settings.sandbox_orchestrator_host or settings.sandbox_vm_host)

    # ══════════════════════════════════════════════════════════════════
    # Path 1: User-managed sandbox lifecycle
    # ══════════════════════════════════════════════════════════════════

    async def create_sandbox(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        config_id: UUID | None = None,
        name: str | None = None,
        description: str | None = None,
        project_id: UUID | None = None,
    ) -> Sandbox:
        """Create a new user-owned sandbox.

        Provisions infrastructure via the orchestrator, then records in DB.
        Enforces per-user sandbox limits.
        """
        if not self._vm_configured():
            raise RuntimeError(
                "Sandbox not configured: set SANDBOX_VM_HOST or orchestrator"
            )

        # ── Enforce sandbox limit ─────────────────────────────────────
        count = await db.scalar(
            select(func.count(Sandbox.id)).where(Sandbox.user_id == user_id)
        )
        if (count or 0) >= DEFAULT_MAX_SANDBOXES_PER_USER:
            raise SandboxLimitReached(count or 0)

        # ── Resolve config ────────────────────────────────────────────
        config: SandboxConfig | None = None
        if config_id:
            config = await db.get(SandboxConfig, config_id)
        os_image, setup_script, persistent = _resolve_config(config)

        # ── Provision via orchestrator ────────────────────────────────
        try:
            data = await self._orchestrator.session_start(
                persistent=persistent,
                setup_script=setup_script,
                os_image=os_image,
                project_id=str(project_id) if project_id else None,
            )
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach sandbox orchestrator at {self._orchestrator._base}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Sandbox orchestrator timed out ({self._orchestrator._base}): {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Orchestrator error: {exc.response.status_code} {exc.response.text}"
            ) from exc

        orch_id = data["sandbox_id"]
        host = data.get("host")
        if not host:
            logger.error("Orchestrator returned no host for sandbox %s", orch_id)
        port = data.get("host_port", 8080)
        auth_token = data["auth_token"]

        # ── Create DB row ─────────────────────────────────────────────
        sandbox = Sandbox(
            id=uuid_module.uuid4(),
            user_id=user_id,
            project_id=project_id,
            sandbox_config_id=config_id,
            name=name or f"sandbox-{orch_id[:8]}",
            description=description,
            orchestrator_sandbox_id=orch_id,
            status="ready",
            host=host,
            port=port,
            auth_token=auth_token,
        )
        db.add(sandbox)
        await db.flush()

        # ── Health probe ──────────────────────────────────────────────
        await self._probe_health(host, port, auth_token)

        return sandbox

    async def assign_to_agent(
        self,
        db: AsyncSession,
        sandbox_id: UUID,
        agent_id: UUID,
        *,
        user_id: UUID | None = None,
    ) -> Sandbox:
        """Assign an unoccupied sandbox to an agent.

        If user_id is provided, verifies ownership before assigning.
        Notifies the orchestrator so it can route traffic.
        """
        sandbox = await self._load_sandbox(db, sandbox_id)
        if user_id and sandbox.user_id != user_id:
            raise SandboxOwnershipError(sandbox_id, user_id)
        if sandbox.agent_id is not None:
            raise SandboxAlreadyAssigned(sandbox_id, sandbox.agent_id)

        sandbox.agent_id = agent_id
        sandbox.status = "assigned"
        sandbox.assigned_at = _utcnow()
        await db.flush()

        # Best-effort orchestrator notification
        try:
            await self._orchestrator.claim(
                sandbox.orchestrator_sandbox_id,
                agent_id=str(agent_id),
                project_id=str(sandbox.project_id) if sandbox.project_id else None,
            )
        except Exception as exc:
            logger.warning("Orchestrator claim notification failed: %s", exc)
            # Don't revert — the DB assignment is authoritative

        return sandbox

    async def unassign_from_agent(
        self,
        db: AsyncSession,
        sandbox_id: UUID,
        *,
        user_id: UUID | None = None,
    ) -> Sandbox:
        """Detach sandbox from its agent. Returns to 'ready' state."""
        sandbox = await self._load_sandbox(db, sandbox_id)
        if user_id and sandbox.user_id != user_id:
            raise SandboxOwnershipError(sandbox_id, user_id)

        sandbox.agent_id = None
        sandbox.status = "ready"
        sandbox.released_at = _utcnow()
        await db.flush()

        # Best-effort orchestrator notification
        try:
            await self._orchestrator.release(sandbox.orchestrator_sandbox_id)
        except Exception as exc:
            logger.warning("Orchestrator release notification failed: %s", exc)

        return sandbox

    async def update_sandbox(
        self,
        db: AsyncSession,
        sandbox_id: UUID,
        user_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        config_id: UUID | None = _SENTINEL,
        project_id: UUID | None = _SENTINEL,
    ) -> Sandbox:
        """Update mutable sandbox properties. Only the owner may update."""
        sandbox = await self._load_sandbox(db, sandbox_id)
        if sandbox.user_id != user_id:
            raise SandboxOwnershipError(sandbox_id, user_id)

        if name is not None:
            sandbox.name = name
        if description is not None:
            sandbox.description = description
        if config_id is not _SENTINEL:
            sandbox.sandbox_config_id = config_id
        if project_id is not _SENTINEL:
            sandbox.project_id = project_id

        await db.flush()
        return sandbox

    async def transfer_ownership(
        self,
        db: AsyncSession,
        sandbox_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> Sandbox:
        """Transfer sandbox to another user. Unassigns any agent first."""
        sandbox = await self._load_sandbox(db, sandbox_id)
        if sandbox.user_id != current_owner_id:
            raise SandboxOwnershipError(sandbox_id, current_owner_id)

        # Unassign agent if present — the new owner may not have access
        if sandbox.agent_id is not None:
            sandbox.agent_id = None
            sandbox.status = "ready"
            sandbox.released_at = _utcnow()

        sandbox.user_id = new_owner_id
        await db.flush()
        return sandbox

    async def clone_sandbox(
        self,
        db: AsyncSession,
        sandbox_id: UUID,
        user_id: UUID,
        *,
        new_name: str | None = None,
    ) -> Sandbox:
        """Clone a sandbox by snapshotting and provisioning a new one.

        The new sandbox is owned by user_id, unassigned, with the same config.
        """
        source = await self._load_sandbox(db, sandbox_id)
        if source.user_id != user_id:
            raise SandboxOwnershipError(sandbox_id, user_id)

        # Create snapshot of source
        snap_data = await self._orchestrator.create_snapshot(
            source.orchestrator_sandbox_id, label=f"clone-from-{sandbox_id}"
        )

        # Provision new sandbox with same config
        new_sandbox = await self.create_sandbox(
            db,
            user_id,
            config_id=source.sandbox_config_id,
            name=new_name or f"{source.name}-clone",
            description=source.description,
            project_id=source.project_id,
        )

        # Restore snapshot into new sandbox
        snapshot_name = snap_data.get("snapshot_name")
        if snapshot_name:
            try:
                await self._orchestrator.restore_snapshot(
                    new_sandbox.orchestrator_sandbox_id, snapshot_name
                )
            except Exception as exc:
                logger.warning("Clone restore failed: %s", exc)

        return new_sandbox

    # ══════════════════════════════════════════════════════════════════
    # Sandbox infrastructure operations
    # ══════════════════════════════════════════════════════════════════

    async def release_to_pool(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Return sandbox to warm pool. Clears agent assignment."""
        try:
            await self._orchestrator.release(sandbox.orchestrator_sandbox_id)
        except Exception as exc:
            logger.warning("Orchestrator release failed: %s", exc)

        sandbox.agent_id = None
        sandbox.status = "idle"
        sandbox.released_at = _utcnow()
        await db.flush()

    async def restart(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Restart pod, keep PVC."""
        await self._orchestrator.restart_sandbox(sandbox.orchestrator_sandbox_id)

    async def destroy(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Permanently delete sandbox from orchestrator and DB."""
        try:
            await self._orchestrator.destroy(sandbox.orchestrator_sandbox_id)
        except Exception as exc:
            logger.warning("Orchestrator destroy failed: %s", exc)

        await db.delete(sandbox)
        await db.flush()

    async def apply_config(self, db: AsyncSession, sandbox: Sandbox) -> dict | None:
        """Run the sandbox's config setup_script on the container."""
        if not sandbox.sandbox_config_id:
            return None
        config = await db.get(SandboxConfig, sandbox.sandbox_config_id)
        if not config or not config.setup_script:
            return None
        return await self._orchestrator.run_setup(
            sandbox.orchestrator_sandbox_id, config.setup_script
        )

    # ── Snapshots ─────────────────────────────────────────────────────

    async def snapshot(
        self, db: AsyncSession, sandbox: Sandbox, label: str
    ) -> SandboxSnapshot:
        """Create a VolumeSnapshot."""
        data = await self._orchestrator.create_snapshot(
            sandbox.orchestrator_sandbox_id, label
        )
        # Read os_image from config, not from sandbox directly
        os_image = DEFAULT_OS_IMAGE
        if sandbox.sandbox_config_id:
            config = await db.get(SandboxConfig, sandbox.sandbox_config_id)
            if config and config.os_image:
                os_image = config.os_image

        snap = SandboxSnapshot(
            sandbox_id=sandbox.id,
            project_id=sandbox.project_id,
            agent_id=sandbox.agent_id,
            k8s_snapshot_name=data.get("snapshot_name"),
            os_image=os_image,
            label=label,
            size_bytes=data.get("size_bytes"),
        )
        db.add(snap)
        await db.flush()
        return snap

    async def restore(
        self, db: AsyncSession, sandbox: Sandbox, snapshot_id: str
    ) -> None:
        """Restore from snapshot."""
        result = await db.execute(
            select(SandboxSnapshot).where(SandboxSnapshot.id == snapshot_id)
        )
        snap = result.scalar_one_or_none()
        if not snap:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        await self._orchestrator.restore_snapshot(
            sandbox.orchestrator_sandbox_id, snap.k8s_snapshot_name
        )

    # ══════════════════════════════════════════════════════════════════
    # Path 2: Sandbox manipulation (shell, VNC, input)
    # ══════════════════════════════════════════════════════════════════

    async def _resolve_host_port(self, sandbox: Sandbox) -> tuple[str, int]:
        """Return (host, port) for reaching a sandbox, using dev tunnel if needed."""
        import os
        if os.getenv("ENV", "").lower() == "development" and not os.getenv("K_SERVICE"):
            from backend.services.sandbox_tunnel import get_tunnel_manager
            try:
                return await get_tunnel_manager().get_host_port(
                    sandbox.orchestrator_sandbox_id, sandbox.port or 8080,
                )
            except Exception as exc:
                logger.warning("Dev tunnel failed for sandbox %s: %s", sandbox.orchestrator_sandbox_id, exc)
        return (sandbox.host, sandbox.port)

    async def execute_command(
        self, sandbox: Sandbox, command: str, timeout: int = 120
    ) -> ShellResult:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.execute_shell(
            host, port, sandbox.auth_token, command, timeout
        )

    async def take_screenshot(self, sandbox: Sandbox) -> bytes:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.get_screenshot(
            host, port, sandbox.auth_token
        )

    async def mouse_move(self, sandbox: Sandbox, x: int, y: int) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.mouse_move(
            host, port, sandbox.auth_token, x, y
        )

    async def mouse_click(
        self,
        sandbox: Sandbox,
        x: int | None = None,
        y: int | None = None,
        button: int = 1,
        click_type: str = "single",
    ) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.mouse_click(
            host, port, sandbox.auth_token,
            x=x, y=y, button=button, click_type=click_type,
        )

    async def mouse_scroll(
        self,
        sandbox: Sandbox,
        x: int | None = None,
        y: int | None = None,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.mouse_scroll(
            host, port, sandbox.auth_token,
            x=x, y=y, direction=direction, clicks=clicks,
        )

    async def mouse_location(self, sandbox: Sandbox) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.mouse_location(
            host, port, sandbox.auth_token
        )

    async def keyboard_press(
        self,
        sandbox: Sandbox,
        keys: str | None = None,
        text: str | None = None,
    ) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.keyboard_press(
            host, port, sandbox.auth_token, keys=keys, text=text
        )

    async def start_recording(self, sandbox: Sandbox) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.start_recording(
            host, port, sandbox.auth_token
        )

    async def stop_recording(self, sandbox: Sandbox) -> bytes:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.stop_recording(
            host, port, sandbox.auth_token
        )

    async def sandbox_health(self, sandbox: Sandbox) -> dict:
        host, port = await self._resolve_host_port(sandbox)
        return await self._client.health_check(
            host, port, sandbox.auth_token
        )

    # ══════════════════════════════════════════════════════════════════
    # Listing & queries
    # ══════════════════════════════════════════════════════════════════

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Sandbox]:
        """List sandboxes owned by a user, with optional filters."""
        stmt = (
            select(Sandbox)
            .where(Sandbox.user_id == user_id)
            .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
            .order_by(Sandbox.created_at.desc())
        )
        if project_id is not None:
            stmt = stmt.where(Sandbox.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Sandbox.status == status)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_project(
        self, db: AsyncSession, project_id: UUID
    ) -> list[Sandbox]:
        """List all sandboxes attached to a project (any owner)."""
        result = await db.execute(
            select(Sandbox)
            .where(Sandbox.project_id == project_id)
            .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
            .order_by(Sandbox.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, sandbox_id: UUID) -> Sandbox | None:
        """Load a sandbox by ID with relationships."""
        result = await db.execute(
            select(Sandbox)
            .where(Sandbox.id == sandbox_id)
            .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
        )
        return result.scalar_one_or_none()

    async def list_images(self) -> list[dict]:
        return await self._orchestrator.list_images()

    # ══════════════════════════════════════════════════════════════════
    # Deprecated: agent-triggered claim flow (backward compat)
    # ══════════════════════════════════════════════════════════════════

    async def ensure_running_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        *,
        persistent: bool | None = None,
    ) -> SandboxMetadata:
        """DEPRECATED — backward compat for orchestrator.ensure_sandbox_for_agent.

        If the agent already has a sandbox, returns it.
        Otherwise, auto-creates one using the agent's user/project context.
        Will be removed once all callers migrate to user-managed sandbox flow.
        """
        if not self._vm_configured():
            logger.warning(
                "SANDBOX_VM_HOST not configured — sandbox offline for agent %s",
                agent.id,
            )
            return SandboxMetadata(
                sandbox_id=f"offline-{agent.id}",
                agent_id=str(agent.id),
                persistent=False,
                status="offline",
                message="Sandbox offline: not configured.",
            )

        # Check if agent already has a sandbox
        existing = await session.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        existing_sandbox = existing.scalar_one_or_none()
        if existing_sandbox:
            return SandboxMetadata(
                sandbox_id=str(existing_sandbox.id),
                agent_id=str(agent.id),
                persistent=False,
                status=existing_sandbox.status,
                host_port=existing_sandbox.port or 0,
                auth_token=existing_sandbox.auth_token or "",
                message=f"Sandbox ready: {existing_sandbox.id}",
            )

        # Auto-create: use agent's project owner as the sandbox owner
        # (maintains backward compat until frontend handles sandbox creation)
        from backend.db.models import Project
        owner_id = agent.user_id if hasattr(agent, "user_id") else None
        if not owner_id:
            proj_result = await session.execute(
                select(Project).where(Project.id == agent.project_id)
            )
            project = proj_result.scalar_one_or_none()
            owner_id = project.owner_id if project else None
        if not owner_id:
            # Last resort: first user
            from backend.db.models import User
            first_user = await session.execute(
                select(User.id).order_by(User.created_at).limit(1)
            )
            owner_id = first_user.scalar_one_or_none()

        if not owner_id:
            raise RuntimeError("Cannot determine owner for auto-created sandbox")

        sandbox = await self.create_sandbox(
            session,
            owner_id,
            project_id=agent.project_id,
        )
        sandbox = await self.assign_to_agent(
            session, sandbox.id, agent.id
        )
        await session.commit()

        return SandboxMetadata(
            sandbox_id=str(sandbox.id),
            agent_id=str(agent.id),
            persistent=False,
            status=sandbox.status,
            host_port=sandbox.port or 0,
            auth_token=sandbox.auth_token or "",
            created=True,
            message=f"Sandbox ready: {sandbox.id}",
        )

    async def close_sandbox(self, session: AsyncSession, agent: Agent) -> None:
        """DEPRECATED — release sandbox by agent reference."""
        sandbox = await session.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        sb = sandbox.scalar_one_or_none()
        if not sb:
            raise SandboxNotFoundError(str(agent.id))
        await self.unassign_from_agent(session, sb.id)
        await session.flush()

    async def execute_command_legacy(
        self,
        session: AsyncSession,
        agent: Agent,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        """DEPRECATED — execute command via agent reference."""
        meta = await self.ensure_running_sandbox(session, agent)
        if meta.status == "offline":
            return ShellResult(
                stdout=f"[Sandbox offline] Cannot execute: {command}",
                exit_code=None,
            )
        result = await session.execute(
            select(Sandbox).where(Sandbox.id == meta.sandbox_id)
        )
        sandbox = result.scalar_one()
        return await self.execute_command(sandbox, command, timeout)

    async def take_screenshot_legacy(
        self, session: AsyncSession, agent: Agent
    ) -> bytes:
        """DEPRECATED — get screenshot via agent reference."""
        sandbox = await session.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        sb = sandbox.scalar_one_or_none()
        if not sb:
            raise SandboxNotFoundError(str(agent.id))
        return await self.take_screenshot(sb)

    # ── Internal helpers ──────────────────────────────────────────────

    async def _load_sandbox(self, db: AsyncSession, sandbox_id: UUID) -> Sandbox:
        """Load sandbox by ID or raise."""
        result = await db.execute(
            select(Sandbox)
            .where(Sandbox.id == sandbox_id)
            .options(selectinload(Sandbox.config))
        )
        sandbox = result.scalar_one_or_none()
        if not sandbox:
            raise SandboxNotFoundError(str(sandbox_id))
        return sandbox

    async def _probe_health(
        self, host: str | None, port: int, auth_token: str | None
    ) -> None:
        """Best-effort health probe on a freshly provisioned sandbox."""
        if not host:
            return
        try:
            await self._client.health_check(host, port, auth_token)
        except Exception as probe_exc:
            logger.warning("Health check failed on new sandbox: %s", probe_exc)
            import asyncio
            await asyncio.sleep(3)
            try:
                await self._client.health_check(host, port, auth_token)
            except Exception:
                logger.error("Sandbox still unhealthy after retry")
