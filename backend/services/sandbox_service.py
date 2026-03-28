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




# ── Orchestrator Client ───────────────────────────────────────────────────

class CapacityExhaustedError(Exception):
    """Pool manager reported capacity exhaustion."""

    def __init__(self, detail: dict):
        self.detail = detail
        resource = detail.get("resource", "unknown")
        super().__init__(f"Capacity exhausted: {resource}")


class OrchestratorClient:
    """Async REST client for the sandbox orchestrator (Grand-VM pool manager).

    v4: Supports dual-backend (headless Docker + desktop QEMU) with
    promote/demote, capacity status, and requires_desktop routing.

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
            if resp.status_code == 404 and agent_id:
                # Grand-VM pool manager uses /assign instead of the older /claim path.
                resp = await client.post(
                    f"{self._base}/sandbox/{sandbox_id}/assign",
                    json={"agent_id": agent_id},
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
        requires_desktop: bool = False,
        setup_script: str | None = None,
        os_image: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        """Ask the orchestrator to provision a new sandbox.

        v4: `requires_desktop=True` routes to QEMU sub-VM instead of Docker.
        Raises CapacityExhaustedError on 503 with structured capacity data.
        """
        body: dict = {
            "persistent": persistent,
            "requires_desktop": requires_desktop,
        }
        if agent_id:
            body["agent_id"] = agent_id
        if setup_script:
            body["setup_script"] = setup_script
        if os_image:
            body["os_image"] = os_image
        if project_id:
            body["project_id"] = project_id
        read_timeout = 300.0 if (setup_script or requires_desktop) else 120.0
        timeout = httpx.Timeout(read_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base}/sandbox/session/start",
                json=body,
                headers=self._headers,
            )
            if resp.status_code == 503:
                try:
                    detail = resp.json()
                except Exception:
                    detail = {"error": "capacity_exhausted"}
                raise CapacityExhaustedError(detail)
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

    # ── v4: Promote / Demote ──────────────────────────────────────────

    async def promote(self, unit_id: str) -> dict:
        """Promote a headless unit to desktop (Docker → QEMU).

        Raises CapacityExhaustedError if desktop budget is full.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base}/session/promote/{unit_id}",
                headers=self._headers,
            )
            if resp.status_code == 503:
                try:
                    detail = resp.json()
                except Exception:
                    detail = {"error": "capacity_exhausted"}
                raise CapacityExhaustedError(detail)
            resp.raise_for_status()
            return resp.json()

    async def demote(self, unit_id: str) -> dict:
        """Demote a desktop unit to headless (QEMU → Docker)."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base}/session/demote/{unit_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── v4: Capacity status ──────────────────────────────────────────

    async def capacity_status(self) -> dict:
        """Get Grand-VM capacity budget snapshot."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/status",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_units(self) -> list[dict]:
        """Get all active units from pool manager."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/units",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def touch_sandbox(self, sandbox_id: str) -> dict:
        """Touch a sandbox to reset its idle timer (v4 idle reaping)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/touch",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()


# ── Helpers ───────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_config(config: SandboxConfig | None) -> tuple[str, str | None, bool, bool]:
    """Extract (os_image, setup_script, persistent, requires_desktop) from a SandboxConfig."""
    if not config:
        return DEFAULT_OS_IMAGE, None, False, False
    return (
        config.os_image or DEFAULT_OS_IMAGE,
        config.setup_script or None,
        bool(config.persistent),
        bool(getattr(config, "requires_desktop", False)),
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
        requires_desktop: bool = False,
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
        os_image, setup_script, persistent, config_requires_desktop = _resolve_config(config)
        # Explicit parameter wins; otherwise fall back to config
        effective_desktop = requires_desktop or config_requires_desktop
        # Desktops are user-managed, long-lived resources — always persistent
        # so the idle reaper doesn't kill them while the user is away.
        if effective_desktop:
            persistent = True

        # ── Provision via orchestrator ────────────────────────────────
        try:
            data = await self._orchestrator.session_start(
                persistent=persistent,
                requires_desktop=effective_desktop,
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
        unit_type = data.get("unit_type", "desktop" if effective_desktop else "headless")

        # ── Create or reclaim DB row ──────────────────────────────────
        # Persistent desktop VMs may be reused by the pool manager, so the
        # orchestrator_sandbox_id can already exist in the DB from a prior
        # session.  Reclaim the record instead of failing with a unique
        # constraint violation.
        existing = (await db.execute(
            select(Sandbox).where(Sandbox.orchestrator_sandbox_id == orch_id)
        )).scalar_one_or_none()

        if existing:
            existing.user_id = user_id
            existing.project_id = project_id
            existing.sandbox_config_id = config_id
            existing.name = name or f"sandbox-{orch_id[:8]}"
            existing.description = description
            existing.unit_type = unit_type
            existing.status = "ready"
            existing.host = host
            existing.port = port
            existing.auth_token = auth_token
            existing.agent_id = None
            existing.assigned_at = None
            existing.released_at = None
            sandbox = existing
        else:
            sandbox = Sandbox(
                id=uuid_module.uuid4(),
                user_id=user_id,
                project_id=project_id,
                sandbox_config_id=config_id,
                name=name or f"sandbox-{orch_id[:8]}",
                description=description,
                orchestrator_sandbox_id=orch_id,
                unit_type=unit_type,
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
    # Agent headless sandbox access (v4.1)
    # ══════════════════════════════════════════════════════════════════

    async def acquire_sandbox_for_agent(
        self,
        db: AsyncSession,
        agent: Agent,
    ) -> Sandbox:
        """Acquire a headless sandbox for an agent (v4.1 D1).

        1. If the agent already has an assigned sandbox, return it.
        2. Otherwise, provision a new *headless* sandbox from the pool and
           assign it to the agent.

        Desktop sandboxes are never auto-provisioned here — only users can
        create desktops via the REST API (D2).

        Raises RuntimeError if the sandbox VM is not configured or if
        provisioning fails.
        """
        # ── 1. Check existing assignment ────────────────────────────────
        existing = await db.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        existing_sandbox = existing.scalar_one_or_none()
        if existing_sandbox:
            from sqlalchemy.orm.attributes import set_committed_value
            set_committed_value(agent, "sandbox", existing_sandbox)
            return existing_sandbox

        # ── 2. Guard: VM must be reachable ──────────────────────────────
        if not self._vm_configured():
            raise RuntimeError(
                "Sandbox VM not configured — cannot acquire sandbox. "
                "Set SANDBOX_VM_HOST or the orchestrator env vars."
            )

        # ── 3. Determine owner for the sandbox ─────────────────────────
        from backend.db.models import Project, User as UserModel

        owner_id = getattr(agent, "user_id", None)
        if not owner_id:
            proj_result = await db.execute(
                select(Project).where(Project.id == agent.project_id)
            )
            project = proj_result.scalar_one_or_none()
            owner_id = project.owner_id if project else None
        if not owner_id:
            first_user = await db.execute(
                select(UserModel.id).order_by(UserModel.created_at).limit(1)
            )
            owner_id = first_user.scalar_one_or_none()
        if not owner_id:
            raise RuntimeError("Cannot determine owner for sandbox provisioning")

        # ── 4. Provision headless sandbox and assign ────────────────────
        sandbox = await self.create_sandbox(
            db,
            owner_id,
            project_id=agent.project_id,
            requires_desktop=False,  # Always headless for agent-acquired
        )
        sandbox = await self.assign_to_agent(db, sandbox.id, agent.id)

        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(agent, "sandbox", sandbox)

        return sandbox

    async def release_agent_sandbox(
        self,
        db: AsyncSession,
        agent: Agent,
    ) -> None:
        """Release an agent's sandbox back to the pool (v4.1 D1).

        Looks up the sandbox assigned to the agent, unassigns it, and
        returns it to the warm pool. Updates the agent's sandbox
        relationship to None.

        Does nothing if the agent has no sandbox.
        """
        result = await db.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        sandbox = result.scalar_one_or_none()
        if not sandbox:
            return

        await self.release_to_pool(db, sandbox)

        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(agent, "sandbox", None)

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

    async def restart(self, db: AsyncSession, sandbox: Sandbox) -> dict:
        """Restart sandbox. If the container is gone, re-provision it.

        Returns a dict with ``action`` ("restarted" or "reprovisioned") so the
        caller can inform the user what actually happened.
        """
        # Try a normal restart first
        try:
            await self._orchestrator.restart_sandbox(
                sandbox.orchestrator_sandbox_id
            )
            sandbox.status = "ready"
            await db.flush()
            return {"action": "restarted"}
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                "Restart failed for %s, will re-provision: %s",
                sandbox.orchestrator_sandbox_id,
                exc,
            )

        # Container is gone — re-provision with the same config
        config: SandboxConfig | None = None
        if sandbox.sandbox_config_id:
            config = await db.get(SandboxConfig, sandbox.sandbox_config_id)
        os_image, setup_script, persistent, config_desktop = _resolve_config(config)
        effective_desktop = sandbox.unit_type == "desktop" or config_desktop

        try:
            data = await self._orchestrator.session_start(
                persistent=persistent,
                requires_desktop=effective_desktop,
                setup_script=setup_script,
                os_image=os_image,
                project_id=str(sandbox.project_id) if sandbox.project_id else None,
                agent_id=str(sandbox.agent_id) if sandbox.agent_id else None,
            )
        except Exception as prov_exc:
            sandbox.status = "unreachable"
            await db.flush()
            raise RuntimeError(
                f"Failed to re-provision sandbox: {prov_exc}"
            ) from prov_exc

        # Update DB record with new connection info
        sandbox.orchestrator_sandbox_id = data["sandbox_id"]
        sandbox.host = data.get("host")
        sandbox.port = data.get("host_port", 8080)
        sandbox.auth_token = data["auth_token"]
        sandbox.unit_type = data.get(
            "unit_type", "desktop" if effective_desktop else "headless"
        )
        sandbox.status = "ready"
        sandbox.released_at = None
        await db.flush()

        await self._probe_health(sandbox.host, sandbox.port, sandbox.auth_token)
        return {"action": "reprovisioned"}

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

    # ══════════════════════════════════════════════════════════════════
    # v4: Promote / Demote / Capacity
    # ══════════════════════════════════════════════════════════════════

    async def promote_to_desktop(
        self, db: AsyncSession, sandbox: Sandbox
    ) -> Sandbox:
        """Promote a headless sandbox to desktop (Docker → QEMU).

        The pool manager handles the full migration: reserve budget, create VM,
        migrate files, destroy container. We just forward the request and update
        the DB record.
        """
        if sandbox.unit_type == "desktop":
            raise ValueError("Sandbox is already a desktop unit")

        data = await self._orchestrator.promote(sandbox.orchestrator_sandbox_id)
        new_id = data.get("new_unit_id", sandbox.orchestrator_sandbox_id)
        sandbox.orchestrator_sandbox_id = new_id
        sandbox.unit_type = "desktop"
        sandbox.host = data.get("host", sandbox.host)
        sandbox.port = data.get("host_port", sandbox.port)
        sandbox.auth_token = data.get("auth_token", sandbox.auth_token)
        await db.flush()
        return sandbox

    async def demote_to_headless(
        self, db: AsyncSession, sandbox: Sandbox
    ) -> Sandbox:
        """Demote a desktop sandbox to headless (QEMU → Docker)."""
        if sandbox.unit_type == "headless":
            raise ValueError("Sandbox is already a headless unit")

        data = await self._orchestrator.demote(sandbox.orchestrator_sandbox_id)
        new_id = data.get("new_unit_id", sandbox.orchestrator_sandbox_id)
        sandbox.orchestrator_sandbox_id = new_id
        sandbox.unit_type = "headless"
        sandbox.host = data.get("host", sandbox.host)
        sandbox.port = data.get("host_port", sandbox.port)
        sandbox.auth_token = data.get("auth_token", sandbox.auth_token)
        await db.flush()
        return sandbox

    async def capacity_status(self) -> dict:
        """Get current Grand-VM capacity budget snapshot."""
        return await self._orchestrator.capacity_status()

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
    # Pool status sync
    # ══════════════════════════════════════════════════════════════════

    # Pool manager status → DB status mapping
    _POOL_STATUS_MAP = {
        "idle": "idle",
        "assigned": "assigned",
        "resetting": "resetting",
        "unhealthy": "unhealthy",
    }

    async def sync_pool_status(
        self, db: AsyncSession, sandboxes: list[Sandbox]
    ) -> None:
        """Best-effort sync of DB sandbox status from pool manager units.

        Queries the pool manager once, cross-references by
        orchestrator_sandbox_id, and updates any rows that have drifted.
        Commits nothing — caller is responsible for flush/commit.
        """
        if not sandboxes:
            return
        try:
            units = await self._orchestrator.list_sandboxes()
        except Exception as exc:
            logger.debug("Pool status sync skipped (pool manager unreachable): %s", exc)
            return

        unit_map: dict[str, str] = {
            u["unit_id"]: u.get("status", "")
            for u in units
            if "unit_id" in u
        }

        for sb in sandboxes:
            pool_status = unit_map.get(sb.orchestrator_sandbox_id)
            if pool_status is None:
                # Unit no longer exists in pool manager
                if sb.status not in ("released", "unhealthy"):
                    sb.status = "released"
                continue
            mapped = self._POOL_STATUS_MAP.get(pool_status)
            if mapped and mapped != sb.status:
                sb.status = mapped

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
