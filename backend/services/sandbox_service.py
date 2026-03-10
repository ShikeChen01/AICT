"""
Sandbox Service — high-level sandbox lifecycle management backed by the
self-hosted VM pool manager.

This module provides:
  - PoolManagerClient: thin REST client for the VM pool manager (port 9090)
  - SandboxService: manages sandbox lifecycle for all agents
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import SandboxNotFoundError
from backend.db.models import Agent
from backend.logging.my_logger import get_logger
from backend.services.sandbox_client import ShellResult, get_sandbox_client

logger = get_logger(__name__)


# ── Pool manager API response ─────────────────────────────────────────────────


@dataclass(slots=True)
class SandboxMetadata:
    """Returned by SandboxService lifecycle methods."""

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


# ── Pool Manager Client ───────────────────────────────────────────────────────


class PoolManagerClient:
    """Thin async REST client for the sandbox orchestrator (GKE or legacy VM)."""

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
        # Longer timeout: setup scripts can install packages, Windows pods
        # can take up to 5 min for Autopilot node provisioning
        timeout = 300.0 if setup_script else 120.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base}/sandbox/session/start",
                json=body,
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

    async def get_sandbox_by_id(self, sandbox_id: str) -> dict:
        """Fetch a single sandbox's metadata from the pool manager."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base}/sandbox/{sandbox_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()


# ── Sandbox Service ───────────────────────────────────────────────────────────


class SandboxService:
    """Manages sandbox lifecycle for agents using GKE orchestrator or legacy VM pool."""

    def __init__(self) -> None:
        self._pool = PoolManagerClient()
        self._client = get_sandbox_client()

    # ── Core lifecycle ────────────────────────────────────────────────────────

    def _vm_configured(self) -> bool:
        return bool(settings.sandbox_orchestrator_host or settings.sandbox_vm_host)

    async def ensure_running_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        *,
        persistent: bool | None = None,
    ) -> SandboxMetadata:
        """
        Ensure an agent has a running sandbox.
        Creates one if missing; returns existing one if already assigned.
        When no VM host is configured (e.g. in tests or local dev without a VM),
        returns an offline placeholder so callers don't crash.
        """
        if not self._vm_configured():
            logger.warning(
                "SANDBOX_VM_HOST not configured — sandbox is offline for agent %s",
                agent.id,
            )
            sandbox_id = agent.sandbox_id or f"offline-{agent.id}"
            agent.sandbox_id = sandbox_id
            await session.flush()
            return SandboxMetadata(
                sandbox_id=sandbox_id,
                agent_id=str(agent.id),
                persistent=bool(agent.sandbox_persist),
                status="offline",
                message="Sandbox offline: SANDBOX_VM_HOST not configured.",
            )

        agent_id = str(agent.id)
        is_persistent = persistent if persistent is not None else bool(agent.sandbox_persist)

        # Load the agent's sandbox config (setup script + os_image) if assigned
        setup_script: str | None = None
        os_image: str | None = None
        if agent.sandbox_config_id:
            from backend.db.models import SandboxConfig
            from sqlalchemy import select
            result = await session.execute(
                select(SandboxConfig.setup_script, SandboxConfig.os_image)
                .where(SandboxConfig.id == agent.sandbox_config_id)
            )
            row = result.one_or_none()
            if row:
                setup_script = row.setup_script or None
                os_image = row.os_image or None

        try:
            data = await self._pool.session_start(
                agent_id,
                persistent=is_persistent,
                setup_script=setup_script,
                os_image=os_image,
                # tenant_id maps to project_id — in AICT, projects are the
                # tenant boundary for sandbox isolation / billing.
                tenant_id=str(agent.project_id) if agent.project_id else None,
                project_id=str(agent.project_id) if agent.project_id else None,
            )
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Pool manager error for agent {agent_id}: "
                f"{exc.response.status_code} {exc.response.text}"
            ) from exc

        sandbox_id: str = data["sandbox_id"]
        host_port: int = data.get("host_port", 8080)
        auth_token: str = data["auth_token"]
        created: bool = data.get("created", False)
        ready: bool = data.get("ready", True)

        # Register (or re-register) this sandbox in the client multiplexer.
        # GKE mode: orchestrator returns a K8s service hostname in "host".
        # Legacy mode: use VM internal/external host + port mapping.
        if self._pool._is_gke and data.get("host"):
            vm_host = data["host"]
            host_port = data.get("host_port", 8080)
        else:
            vm_host = settings.sandbox_vm_internal_host or settings.sandbox_vm_host

        self._client.register(
            sandbox_id=sandbox_id,
            vm_host=vm_host,
            host_port=host_port,
            auth_token=auth_token,
        )

        # Verify the sandbox is actually reachable from this backend process.
        # The pool manager checks health via 127.0.0.1 (localhost) but the
        # backend connects via the external VM host — firewalls, DNS, or a
        # not-yet-ready container can make the external path fail even when
        # the local one succeeds.
        if not ready:
            logger.warning(
                "Pool manager reported sandbox %s as not ready — "
                "container may still be starting",
                sandbox_id,
            )
        try:
            await self._client.health_check(sandbox_id)
        except Exception as probe_exc:
            logger.warning(
                "Sandbox %s registered but health probe failed (%s) — "
                "will retry once after brief delay",
                sandbox_id,
                probe_exc,
            )
            # Brief back-off: the container may still be booting
            import asyncio
            await asyncio.sleep(3)
            try:
                await self._client.health_check(sandbox_id)
            except Exception:
                logger.error(
                    "Sandbox %s still unreachable after retry — "
                    "returning metadata but sandbox may be unhealthy",
                    sandbox_id,
                )

        prev_id = agent.sandbox_id
        restarted = bool(prev_id and prev_id != sandbox_id)
        agent.sandbox_id = sandbox_id
        if persistent is not None:
            agent.sandbox_persist = persistent
        await session.flush()

        msg = (
            f"Sandbox created: {sandbox_id}"
            if created
            else f"Sandbox ready: {sandbox_id}"
        )
        return SandboxMetadata(
            sandbox_id=sandbox_id,
            agent_id=agent_id,
            persistent=bool(agent.sandbox_persist),
            status="running",
            host_port=host_port,
            auth_token=auth_token,
            created=created,
            restarted=restarted,
            previous_sandbox_id=prev_id if restarted else None,
            message=msg,
        )

    async def get_sandbox(self, session: AsyncSession, agent: Agent) -> SandboxMetadata:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return SandboxMetadata(
            sandbox_id=agent.sandbox_id,
            agent_id=str(agent.id),
            persistent=bool(agent.sandbox_persist),
            status="unknown",
        )

    async def create_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        persistent: bool,
    ) -> SandboxMetadata:
        return await self.ensure_running_sandbox(session, agent, persistent=persistent)

    async def close_sandbox(self, session: AsyncSession, agent: Agent) -> None:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))

        agent_id = str(agent.id)
        sandbox_id = agent.sandbox_id

        try:
            await self._pool.session_end(agent_id)
        except Exception as exc:
            logger.warning("Failed to end session for agent %s: %s", agent_id, exc)

        # Unregister from client multiplexer
        self._client.unregister(sandbox_id)

        agent.sandbox_id = None
        await session.flush()

    # ── Execution operations ──────────────────────────────────────────────────

    async def execute_command(
        self,
        session: AsyncSession,
        agent: Agent,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        """
        Ensure the sandbox is running then execute a shell command.
        Handles sandbox creation/reconnection transparently.
        """
        meta = await self.ensure_running_sandbox(session, agent)
        if meta.status == "offline":
            return ShellResult(
                stdout=f"[Sandbox offline] Cannot execute: {command}",
                exit_code=None,
            )
        sandbox_id = meta.sandbox_id
        return await self._client.execute_shell(sandbox_id, command, timeout=timeout)

    async def take_screenshot(self, agent: Agent) -> bytes:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.get_screenshot(agent.sandbox_id)

    async def mouse_move(self, agent: Agent, x: int, y: int) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.mouse_move(agent.sandbox_id, x, y)

    async def mouse_click(
        self,
        agent: Agent,
        x: int | None = None,
        y: int | None = None,
        button: int = 1,
        click_type: str = "single",
    ) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.mouse_click(
            agent.sandbox_id, x=x, y=y, button=button, click_type=click_type,
        )

    async def mouse_scroll(
        self,
        agent: Agent,
        x: int | None = None,
        y: int | None = None,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.mouse_scroll(
            agent.sandbox_id, x=x, y=y, direction=direction, clicks=clicks,
        )

    async def mouse_location(self, agent: Agent) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.mouse_location(agent.sandbox_id)

    async def keyboard_press(
        self,
        agent: Agent,
        keys: str | None = None,
        text: str | None = None,
    ) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.keyboard_press(agent.sandbox_id, keys=keys, text=text)

    async def start_recording(self, agent: Agent) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.start_recording(agent.sandbox_id)

    async def stop_recording(self, agent: Agent) -> bytes:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.stop_recording(agent.sandbox_id)

    async def sandbox_health(
        self,
        agent: Agent,
        session: AsyncSession | None = None,
    ) -> dict:
        """Check sandbox health.  Optionally pass a DB session to enable
        automatic re-registration when the in-memory connection is missing
        (e.g. after a backend process restart).
        """
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))

        # If the connection is not registered in the multiplexer (backend
        # restarted, losing the in-memory singleton), re-register via
        # ensure_running_sandbox before attempting the health check.
        if not self._client.has_connection(agent.sandbox_id) and session is not None:
            logger.info(
                "Sandbox %s not registered in multiplexer — re-registering via pool manager",
                agent.sandbox_id,
            )
            await self.ensure_running_sandbox(session, agent)

        try:
            return await self._client.health_check(agent.sandbox_id)
        except Exception:
            # Connection exists but request failed — try re-registering once
            if session is not None:
                logger.warning(
                    "Health check failed for sandbox %s — re-registering and retrying",
                    agent.sandbox_id,
                )
                await self.ensure_running_sandbox(session, agent)
                return await self._client.health_check(agent.sandbox_id)
            raise

    # ── Management operations ────────────────────────────────────────────────

    async def list_all_sandboxes(self) -> list[dict]:
        """List all sandboxes from the pool manager."""
        if not self._vm_configured():
            return []
        return await self._pool.list_sandboxes()

    async def restart_sandbox(self, agent: Agent) -> dict:
        """Restart a sandbox container (keeps volume / installed apps)."""
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._pool.restart_sandbox(agent.sandbox_id)

    async def set_sandbox_persistent(
        self,
        session: AsyncSession,
        agent: Agent,
        persistent: bool,
    ) -> dict:
        """Toggle the persistent flag on a sandbox."""
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        result = await self._pool.set_persistent(agent.sandbox_id, persistent)
        agent.sandbox_persist = persistent
        await session.flush()
        return result

    async def destroy_sandbox(self, session: AsyncSession, agent: Agent) -> dict:
        """Permanently destroy a sandbox and its volume."""
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        sandbox_id = agent.sandbox_id
        result = await self._pool.destroy(sandbox_id)
        self._client.unregister(sandbox_id)
        agent.sandbox_id = None
        agent.sandbox_persist = False
        await session.flush()
        return result

    async def apply_config(self, session: AsyncSession, agent: Agent) -> dict:
        """Run the agent's sandbox config setup script on its current sandbox."""
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        if not agent.sandbox_config_id:
            return {"ok": True, "skipped": True, "message": "No config assigned"}
        from backend.db.models import SandboxConfig
        from sqlalchemy import select
        result = await session.execute(
            select(SandboxConfig.setup_script).where(SandboxConfig.id == agent.sandbox_config_id)
        )
        script = result.scalar_one_or_none()
        if not script:
            return {"ok": True, "skipped": True, "message": "Config has empty setup script"}
        return await self._pool.run_setup(agent.sandbox_id, script)
