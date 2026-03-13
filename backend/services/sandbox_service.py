"""
Sandbox Service — high-level sandbox lifecycle management backed by the
warm pool orchestrator with DB persistence.

This module provides:
  - OrchestratorClient: async REST client for the warm pool orchestrator
  - SandboxService: manages sandbox lifecycle via DB + orchestrator integration
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.core.exceptions import SandboxNotFoundError
from backend.db.models import Agent, Sandbox, SandboxConfig, SandboxSnapshot
from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import ShellResult, SandboxClient

logger = get_logger(__name__)


# ── API response dataclass ─────────────────────────────────────────────────

@dataclass(slots=True)
class SandboxMetadata:
    """Backward-compatible metadata returned by lifecycle methods."""

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


# ── Orchestrator Client ────────────────────────────────────────────────────

class OrchestratorClient:
    """Async REST client for the sandbox orchestrator (GKE or legacy VM)."""

    def __init__(self) -> None:
        # Prefer GKE orchestrator when configured; fall back to legacy VM
        if settings.sandbox_orchestrator_host:
            host = settings.sandbox_orchestrator_host
            port = settings.sandbox_orchestrator_port
            token = settings.sandbox_orchestrator_token
        else:
            host = settings.sandbox_vm_internal_host or settings.sandbox_vm_host
            port = settings.sandbox_vm_pool_port
            token = settings.sandbox_vm_master_token

        self._base = f"http://{host}:{port}/api"
        self._headers = {
            "Authorization": f"Bearer {token}",
        }
        self._is_gke = bool(settings.sandbox_orchestrator_host)

    # ── Warm pool (new) ────────────────────────────────────────────────────

    async def provision_warm(self, os_image: str = "ubuntu-22.04") -> dict:
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
        agent_id: str,
        project_id: str | None = None,
        setup_script: str | None = None,
    ) -> dict:
        """Claim an idle sandbox from the pool and assign to agent."""
        body: dict = {"agent_id": agent_id}
        if project_id:
            body["project_id"] = project_id
        if setup_script:
            body["setup_script"] = setup_script
        async with httpx.AsyncClient(timeout=300.0) as client:
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
        """Get warm pool metrics (idle ratios, provisioned count)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/pool/metrics",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Snapshot operations ────────────────────────────────────────────────

    async def create_snapshot(self, sandbox_id: str, label: str = "") -> dict:
        """Create a VolumeSnapshot for the sandbox."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/snapshot",
                json={"label": label},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def restore_snapshot(self, sandbox_id: str, snapshot_name: str) -> dict:
        """Restore a sandbox from a snapshot."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/restore",
                json={"snapshot_name": snapshot_name},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_snapshots(self, sandbox_id: str) -> list[dict]:
        """List all snapshots for a sandbox."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/{sandbox_id}/snapshots",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Legacy session endpoints (still work) ──────────────────────────────

    async def session_start(
        self,
        agent_id: str,
        persistent: bool = False,
        setup_script: str | None = None,
        os_image: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> dict:
        body: dict = {"agent_id": agent_id, "persistent": persistent}
        if setup_script:
            body["setup_script"] = setup_script
        if os_image:
            body["os_image"] = os_image
        if tenant_id:
            body["tenant_id"] = tenant_id
        if project_id:
            body["project_id"] = project_id
        timeout = 300.0 if setup_script else 120.0
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
            resp = await client.get(f"{self._base}/sandbox/list", headers=self._headers)
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
        """Run a setup script on an existing sandbox."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/{sandbox_id}/run-setup",
                json={"setup_script": setup_script},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_sandbox_by_id(self, sandbox_id: str) -> dict:
        """Fetch a single sandbox's metadata from the orchestrator."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/{sandbox_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_images(self) -> list[dict]:
        """Fetch the OS image catalog from the orchestrator."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/images",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()


# ── Sandbox Service ────────────────────────────────────────────────────────

class SandboxService:
    """Manages sandbox lifecycle via DB + orchestrator.

    Handles claim/release from warm pool, snapshots, shell/input execution.
    """

    def __init__(self) -> None:
        self._orchestrator = OrchestratorClient()
        self._client = SandboxClient()  # stateless shell client

    def _vm_configured(self) -> bool:
        return bool(settings.sandbox_orchestrator_host or settings.sandbox_vm_host)

    # ── Sandbox lifecycle ──────────────────────────────────────────────────

    async def claim(self, db: AsyncSession, agent: Agent) -> Sandbox:
        """Claim idle sandbox from warm pool for agent.

        Steps:
        1. Check if agent already has sandbox via DB relationship
        2. Query for idle sandbox matching agent's os_image preference
        3. If found: update DB row (agent_id, status), call orchestrator claim
        4. If not found: call orchestrator session_start, create DB row
        5. Run setup script if agent has sandbox_config
        """
        if not self._vm_configured():
            raise RuntimeError("Sandbox not configured: SANDBOX_VM_HOST or orchestrator not set")

        # Check if agent already has a sandbox via explicit query
        # (avoids lazy-load issues in async context)
        existing = await db.execute(
            select(Sandbox).where(Sandbox.agent_id == agent.id)
        )
        existing_sandbox = existing.scalar_one_or_none()
        if existing_sandbox:
            return existing_sandbox

        # Load agent's config to get os_image preference
        os_image = "ubuntu-22.04"
        setup_script = None
        if agent.sandbox_config_id:
            result = await db.execute(
                select(SandboxConfig).where(SandboxConfig.id == agent.sandbox_config_id)
            )
            config = result.scalar_one_or_none()
            if config:
                if config.os_image:
                    os_image = config.os_image
                if config.setup_script:
                    setup_script = config.setup_script

        # Try to claim an idle sandbox from the pool
        idle_result = await db.execute(
            select(Sandbox)
            .where(
                Sandbox.project_id == agent.project_id,
                Sandbox.agent_id.is_(None),
                Sandbox.status == "idle",
                Sandbox.os_image == os_image,
            )
            .limit(1)
        )
        idle_sandbox = idle_result.scalar_one_or_none()

        if idle_sandbox:
            # Claim the idle sandbox
            idle_sandbox.agent_id = agent.id
            idle_sandbox.status = "assigned"
            idle_sandbox.assigned_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            await db.flush()

            # Notify orchestrator
            try:
                await self._orchestrator.claim(
                    str(idle_sandbox.orchestrator_sandbox_id),
                    str(agent.id),
                    project_id=str(agent.project_id),
                    setup_script=setup_script,
                )
            except Exception as exc:
                logger.error("Orchestrator claim failed: %s", exc)
                # Revert the DB update
                idle_sandbox.agent_id = None
                idle_sandbox.status = "idle"
                await db.flush()
                raise

            await db.commit()
            return idle_sandbox

        # No idle sandbox available: create a new one via orchestrator
        # Determine persistence by agent role
        from backend.services.orchestrator import sandbox_should_persist
        persistent = sandbox_should_persist(agent.role) if agent.role else False
        try:
            data = await self._orchestrator.session_start(
                agent_id=str(agent.id),
                persistent=persistent,
                setup_script=setup_script,
                os_image=os_image,
                project_id=str(agent.project_id),
            )
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Orchestrator error: {exc.response.status_code} {exc.response.text}"
            ) from exc

        sandbox_id = data["sandbox_id"]
        host = data.get("host") or (settings.sandbox_vm_internal_host or settings.sandbox_vm_host)
        port = data.get("host_port", 8080)
        auth_token = data["auth_token"]

        # Create DB row with a fresh UUID
        import uuid as uuid_module
        sandbox = Sandbox(
            id=uuid_module.uuid4(),
            project_id=agent.project_id,
            agent_id=agent.id,
            sandbox_config_id=agent.sandbox_config_id,
            orchestrator_sandbox_id=sandbox_id,
            os_image=os_image,
            setup_script=setup_script,
            persistent=persistent,
            status="assigned",
            host=host,
            port=port,
            auth_token=auth_token,
            assigned_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )
        db.add(sandbox)
        await db.flush()

        # Health check
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

        await db.commit()
        return sandbox

    async def release(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Return sandbox to warm pool."""
        try:
            await self._orchestrator.release(sandbox.orchestrator_sandbox_id)
        except Exception as exc:
            logger.warning("Orchestrator release failed: %s", exc)

        sandbox.agent_id = None
        sandbox.status = "idle"
        sandbox.released_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        await db.flush()
        await db.commit()

    async def restart(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Restart pod, keep PVC."""
        await self._orchestrator.restart_sandbox(sandbox.orchestrator_sandbox_id)
        await db.commit()

    async def destroy(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Permanently delete sandbox."""
        try:
            await self._orchestrator.destroy(sandbox.orchestrator_sandbox_id)
        except Exception as exc:
            logger.warning("Orchestrator destroy failed: %s", exc)

        await db.delete(sandbox)
        await db.commit()

    async def snapshot(self, db: AsyncSession, sandbox: Sandbox, label: str) -> SandboxSnapshot:
        """Create VolumeSnapshot."""
        data = await self._orchestrator.create_snapshot(sandbox.orchestrator_sandbox_id, label)
        snapshot_name = data.get("snapshot_name")
        size_bytes = data.get("size_bytes")

        snapshot = SandboxSnapshot(
            sandbox_id=sandbox.id,
            project_id=sandbox.project_id,
            agent_id=sandbox.agent_id,
            k8s_snapshot_name=snapshot_name,
            os_image=sandbox.os_image,
            label=label,
            size_bytes=size_bytes,
        )
        db.add(snapshot)
        await db.flush()
        await db.commit()
        return snapshot

    async def restore(self, db: AsyncSession, sandbox: Sandbox, snapshot_id: str) -> None:
        """Restore from snapshot."""
        result = await db.execute(
            select(SandboxSnapshot).where(SandboxSnapshot.id == snapshot_id)
        )
        snapshot = result.scalar_one_or_none()
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        await self._orchestrator.restore_snapshot(
            sandbox.orchestrator_sandbox_id,
            snapshot.k8s_snapshot_name,
        )
        await db.commit()

    # ── Shell/input execution ──────────────────────────────────────────────

    async def execute_command(
        self,
        sandbox: Sandbox,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        return await self._client.execute_shell(
            sandbox.host,
            sandbox.port,
            sandbox.auth_token,
            command,
            timeout,
        )

    async def take_screenshot(self, sandbox: Sandbox) -> bytes:
        return await self._client.get_screenshot(sandbox.host, sandbox.port, sandbox.auth_token)

    async def mouse_move(self, sandbox: Sandbox, x: int, y: int) -> dict:
        return await self._client.mouse_move(sandbox.host, sandbox.port, sandbox.auth_token, x, y)

    async def mouse_click(
        self,
        sandbox: Sandbox,
        x: int | None = None,
        y: int | None = None,
        button: int = 1,
        click_type: str = "single",
    ) -> dict:
        return await self._client.mouse_click(
            sandbox.host,
            sandbox.port,
            sandbox.auth_token,
            x=x,
            y=y,
            button=button,
            click_type=click_type,
        )

    async def mouse_scroll(
        self,
        sandbox: Sandbox,
        x: int | None = None,
        y: int | None = None,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict:
        return await self._client.mouse_scroll(
            sandbox.host,
            sandbox.port,
            sandbox.auth_token,
            x=x,
            y=y,
            direction=direction,
            clicks=clicks,
        )

    async def mouse_location(self, sandbox: Sandbox) -> dict:
        return await self._client.mouse_location(sandbox.host, sandbox.port, sandbox.auth_token)

    async def keyboard_press(
        self,
        sandbox: Sandbox,
        keys: str | None = None,
        text: str | None = None,
    ) -> dict:
        return await self._client.keyboard_press(
            sandbox.host,
            sandbox.port,
            sandbox.auth_token,
            keys=keys,
            text=text,
        )

    async def start_recording(self, sandbox: Sandbox) -> dict:
        return await self._client.start_recording(sandbox.host, sandbox.port, sandbox.auth_token)

    async def stop_recording(self, sandbox: Sandbox) -> bytes:
        return await self._client.stop_recording(sandbox.host, sandbox.port, sandbox.auth_token)

    async def sandbox_health(self, sandbox: Sandbox) -> dict:
        return await self._client.health_check(sandbox.host, sandbox.port, sandbox.auth_token)

    # ── Listing ────────────────────────────────────────────────────────────

    async def list_sandboxes(self, db: AsyncSession, project_id) -> list[Sandbox]:
        """List sandboxes for a project from DB."""
        result = await db.execute(
            select(Sandbox)
            .where(Sandbox.project_id == project_id)
            .options(selectinload(Sandbox.agent), selectinload(Sandbox.config))
        )
        return list(result.scalars().all())

    async def list_images(self) -> list[dict]:
        return await self._orchestrator.list_images()

    # ── Legacy API compatibility ───────────────────────────────────────────

    async def ensure_running_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        *,
        persistent: bool | None = None,
    ) -> SandboxMetadata:
        """Legacy API: ensure sandbox exists and return metadata.

        This wraps the new claim() method for backward compatibility.
        """
        if not self._vm_configured():
            logger.warning(
                "SANDBOX_VM_HOST not configured — sandbox is offline for agent %s",
                agent.id,
            )
            sandbox_id = f"offline-{agent.id}"
            return SandboxMetadata(
                sandbox_id=sandbox_id,
                agent_id=str(agent.id),
                persistent=False,
                status="offline",
                message="Sandbox offline: SANDBOX_VM_HOST not configured.",
            )

        # Note: persistent parameter is now ignored; use sandbox.persistent from claim()
        sandbox = await self.claim(session, agent)
        return SandboxMetadata(
            sandbox_id=str(sandbox.id),
            agent_id=str(agent.id),
            persistent=sandbox.persistent,
            status=sandbox.status,
            host_port=sandbox.port,
            auth_token=sandbox.auth_token,
            created=True,
            message=f"Sandbox ready: {sandbox.id}",
        )

    async def create_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        persistent: bool,
    ) -> SandboxMetadata:
        """Legacy API."""
        return await self.ensure_running_sandbox(session, agent, persistent=persistent)

    async def execute_command_legacy(
        self,
        session: AsyncSession,
        agent: Agent,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        """Legacy API: execute command by agent."""
        meta = await self.ensure_running_sandbox(session, agent)
        if meta.status == "offline":
            return ShellResult(
                stdout=f"[Sandbox offline] Cannot execute: {command}",
                exit_code=None,
            )
        # Fetch the sandbox from DB
        result = await session.execute(
            select(Sandbox).where(Sandbox.id == meta.sandbox_id)
        )
        sandbox = result.scalar_one()
        return await self.execute_command(sandbox, command, timeout)

    async def take_screenshot_legacy(self, session: AsyncSession, agent: Agent) -> bytes:
        """Legacy API: get screenshot by agent."""
        # Get sandbox from relationship; if not loaded, query it
        sandbox = agent.sandbox
        if not sandbox:
            result = await session.execute(
                select(Sandbox).where(Sandbox.agent_id == agent.id)
            )
            sandbox = result.scalar_one_or_none()
        if not sandbox:
            raise SandboxNotFoundError(str(agent.id))
        return await self.take_screenshot(sandbox)

    async def close_sandbox(self, session: AsyncSession, agent: Agent) -> None:
        """Legacy API: release sandbox."""
        # Get sandbox from relationship; if not loaded, query it
        sandbox = agent.sandbox
        if not sandbox:
            result = await session.execute(
                select(Sandbox).where(Sandbox.agent_id == agent.id)
            )
            sandbox = result.scalar_one_or_none()
        if not sandbox:
            raise SandboxNotFoundError(str(agent.id))

        await self.release(session, sandbox)
        await session.flush()
