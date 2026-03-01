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
    """Thin async REST client for the VM-side pool manager."""

    def __init__(self) -> None:
        self._base = (
            f"http://{settings.sandbox_vm_host}:{settings.sandbox_vm_pool_port}/api"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.sandbox_vm_master_token}",
        }

    async def session_start(self, agent_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base}/sandbox/session/start",
                json={"agent_id": agent_id},
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


# ── Sandbox Service ───────────────────────────────────────────────────────────


class SandboxService:
    """Manages sandbox lifecycle for agents using the self-hosted VM pool."""

    def __init__(self) -> None:
        self._pool = PoolManagerClient()
        self._client = get_sandbox_client()

    # ── Core lifecycle ────────────────────────────────────────────────────────

    def _vm_configured(self) -> bool:
        return bool(settings.sandbox_vm_host)

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
        try:
            data = await self._pool.session_start(agent_id)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Pool manager error for agent {agent_id}: "
                f"{exc.response.status_code} {exc.response.text}"
            ) from exc

        sandbox_id: str = data["sandbox_id"]
        host_port: int = data["host_port"]
        auth_token: str = data["auth_token"]
        created: bool = data.get("created", False)

        # Register (or re-register) this sandbox in the client multiplexer
        self._client.register(
            sandbox_id=sandbox_id,
            vm_host=settings.sandbox_vm_host,
            host_port=host_port,
            auth_token=auth_token,
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

    async def sandbox_health(self, agent: Agent) -> dict:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return await self._client.health_check(agent.sandbox_id)
