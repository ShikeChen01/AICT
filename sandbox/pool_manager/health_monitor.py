"""Background health monitor — pings each container and manages unhealthy ones."""

from __future__ import annotations

import asyncio

import httpx

from config import (
    ASSIGNED_TTL_SECONDS,
    HEALTH_CHECK_FAIL_THRESHOLD,
    HEALTH_CHECK_INTERVAL_SECONDS,
    IDLE_TTL_SECONDS,
)
from docker_manager import DockerManager
from models import PoolState, SandboxState
from port_allocator import PortAllocator


class HealthMonitor:
    def __init__(self, pool: PoolState, docker: DockerManager, ports: PortAllocator) -> None:
        self._pool = pool
        self._docker = docker
        self._ports = ports
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)
            try:
                await self._check_all()
            except Exception as exc:
                print(f"[health-monitor] ERROR: {exc}")

    async def _check_all(self) -> None:
        sandboxes = self._pool.all()
        for s in sandboxes:
            await self._check_one(s)

    async def _check_one(self, s: SandboxState) -> None:
        # "resetting" slots are between destroy and recreate — Docker doesn't
        # have a running container to ping yet.  Skip and let the background
        # reset task in main.py drive the transition to "idle".
        if s.status == "resetting":
            return

        # TTL-based idle cleanup
        if s.status == "idle" and s.idle_seconds() > IDLE_TTL_SECONDS:
            print(f"[health-monitor] Evicting idle sandbox {s.sandbox_id} (TTL exceeded)")
            await self._evict(s)
            return

        # Zombie assigned-sandbox guard.  If an agent's session_end call
        # timed out or the backend crashed without calling session_end, the
        # slot stays "assigned" even though no live agent holds it.  Release
        # it back to the reset pipeline so the slot becomes available again.
        if s.status == "assigned" and s.idle_seconds() > ASSIGNED_TTL_SECONDS:
            print(
                f"[health-monitor] Releasing zombie assigned sandbox {s.sandbox_id} "
                f"(idle for {s.idle_seconds():.0f}s > ASSIGNED_TTL={ASSIGNED_TTL_SECONDS}s)"
            )
            self._pool.mark_resetting(s.sandbox_id)
            asyncio.create_task(self._reset_and_idle(s))
            return

        # Health ping
        healthy = await self._ping(s)
        if healthy:
            s.health_failures = 0
            self._pool.update(s)
            return

        s.health_failures += 1
        print(
            f"[health-monitor] Sandbox {s.sandbox_id} health failure "
            f"{s.health_failures}/{HEALTH_CHECK_FAIL_THRESHOLD}"
        )

        if s.health_failures >= HEALTH_CHECK_FAIL_THRESHOLD:
            s.status = "unhealthy"
            self._pool.update(s)
            await self._restart(s)

    async def _ping(self, s: SandboxState) -> bool:
        url = f"http://127.0.0.1:{s.host_port}/health"
        headers = {"Authorization": f"Bearer {s.auth_token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.status_code == 200
        except Exception:
            return False

    async def _reset_and_idle(self, s: SandboxState) -> None:
        """Reset a sandbox container and mark it idle once the new instance is ready."""
        sandbox_id = s.sandbox_id
        print(f"[health-monitor] Resetting sandbox {sandbox_id} → idle …")
        loop = asyncio.get_event_loop()
        try:
            new_id = await loop.run_in_executor(
                None,
                self._docker.reset_container,
                sandbox_id,
                s.host_port,
                s.auth_token,
                s.volume_name,
            )
            # Re-fetch in case the object was updated while the executor ran.
            current = self._pool.get(sandbox_id)
            if current:
                current.container_id = new_id
                self._pool.update(current)

            # Wait for the new container to be reachable before advertising it.
            url = f"http://127.0.0.1:{s.host_port}/health"
            headers = {"Authorization": f"Bearer {s.auth_token}"}
            deadline = asyncio.get_event_loop().time() + 30.0
            ready = False
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            ready = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(1.0)

            if not ready:
                print(f"[health-monitor] Sandbox {sandbox_id} not ready after reset — evicting")
                await self._evict(self._pool.get(sandbox_id) or s)
                return

            self._pool.release(sandbox_id)
            print(f"[health-monitor] Sandbox {sandbox_id} reset complete → idle")
        except Exception as exc:
            print(f"[health-monitor] Reset failed for {sandbox_id}: {exc} — evicting")
            await self._evict(self._pool.get(sandbox_id) or s)

    async def _restart(self, s: SandboxState) -> None:
        """Restart an unhealthy container, keeping its assignment if it had one."""
        print(f"[health-monitor] Restarting container for sandbox {s.sandbox_id}...")
        loop = asyncio.get_event_loop()
        try:
            new_id = await loop.run_in_executor(
                None,
                self._docker.reset_container,
                s.sandbox_id,
                s.host_port,
                s.auth_token,
                s.volume_name,
            )
            s.container_id = new_id
            s.health_failures = 0
            # Preserve "assigned" only when an agent still holds the sandbox.
            # If assigned_agent_id was cleared (zombie), default to idle.
            s.status = "assigned" if s.assigned_agent_id else "idle"
            self._pool.update(s)
            print(f"[health-monitor] Sandbox {s.sandbox_id} restarted → {new_id[:12]}")
        except Exception as exc:
            print(f"[health-monitor] Restart failed for {s.sandbox_id}: {exc} — evicting")
            await self._evict(s)

    async def _evict(self, s: SandboxState) -> None:
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._docker.destroy_container, s.sandbox_id)
            await loop.run_in_executor(None, self._docker.remove_volume, s.volume_name)
        except Exception as exc:
            print(f"[health-monitor] Evict error for {s.sandbox_id}: {exc}")
        finally:
            self._ports.release(s.host_port)
            self._pool.remove(s.sandbox_id)
