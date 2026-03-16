"""Health monitor — v4 dual-backend (Docker + QEMU) with idle reaping.

Two independent background loops:
  1. Health check (every 30s): ping each unit, restart on 3 consecutive failures.
  2. Idle sweep (every 10 min): destroy temporary units idle > 5 min.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx

import config
from capacity_budget import CapacityBudget
from models import PoolState, UnitState, UnitStatus, UnitType

if TYPE_CHECKING:
    from docker_manager import DockerManager
    from vm_manager import VMManager


class HealthMonitor:
    """Background health checking and idle reaping for both compute backends."""

    def __init__(
        self,
        pool: PoolState,
        docker: "DockerManager",
        vm: "VMManager | None",
        ports: "PortAllocator",
        budget: CapacityBudget,
    ) -> None:
        from port_allocator import PortAllocator

        self._pool = pool
        self._docker = docker
        self._vm = vm
        self._ports: PortAllocator = ports
        self._budget = budget
        self._health_task: asyncio.Task | None = None
        self._sweep_task: asyncio.Task | None = None

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        self._health_task = loop.create_task(self._health_loop())
        self._sweep_task = loop.create_task(self._sweep_loop())

    def stop(self) -> None:
        for task in (self._health_task, self._sweep_task):
            if task:
                task.cancel()

    # ── Health check loop ─────────────────────────────────────────────────────

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(config.HEALTH_CHECK_INTERVAL_SECONDS)
            try:
                await self._check_all_health()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[health-monitor] ERROR in health loop: {exc}")

    async def _check_all_health(self) -> None:
        for u in self._pool.all():
            if u.status in (UnitStatus.RESETTING.value, UnitStatus.PROMOTING.value, UnitStatus.DEMOTING.value):
                continue

            if u.status == UnitStatus.UNHEALTHY.value:
                print(f"[health-monitor] Evicting permanently unhealthy unit {u.unit_id} ({u.unit_type})")
                await self._evict(u)
                continue

            # Zombie guard: assigned > ASSIGNED_TTL without commands
            if (
                u.status == UnitStatus.ASSIGNED.value
                and not u.persistent
                and u.idle_seconds() > config.ASSIGNED_TTL_SECONDS
            ):
                print(
                    f"[health-monitor] Releasing zombie unit {u.unit_id} "
                    f"(idle {u.idle_seconds():.0f}s > {config.ASSIGNED_TTL_SECONDS}s)"
                )
                self._pool.mark_resetting(u.unit_id)
                asyncio.create_task(self._reset_unit(u))
                continue

            healthy = await self._ping(u)
            if healthy:
                if u.health_failures > 0:
                    u.health_failures = 0
                    self._pool.update(u)
                continue

            u.health_failures += 1
            print(
                f"[health-monitor] Unit {u.unit_id} ({u.unit_type}) health failure "
                f"{u.health_failures}/{config.HEALTH_CHECK_FAIL_THRESHOLD}"
            )

            if u.health_failures >= config.HEALTH_CHECK_FAIL_THRESHOLD:
                u.status = UnitStatus.UNHEALTHY.value
                self._pool.update(u)
                await self._restart(u)

    # ── Idle sweep loop ───────────────────────────────────────────────────────

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(config.SWEEP_INTERVAL_SECONDS)
            try:
                await self._sweep_idle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[health-monitor] ERROR in sweep loop: {exc}")

    async def _sweep_idle(self) -> None:
        """Destroy temporary units that have been idle beyond the threshold."""
        for u in self._pool.all():
            if u.persistent:
                continue
            if u.status not in (UnitStatus.IDLE.value, UnitStatus.ASSIGNED.value):
                continue

            idle_secs = u.command_idle_seconds()
            if idle_secs > config.IDLE_THRESHOLD_SECONDS:
                print(
                    f"[health-monitor] Reaping idle unit {u.unit_id} ({u.unit_type}) "
                    f"— no commands for {idle_secs:.0f}s"
                )
                await self._evict(u)

    # ── Ping ──────────────────────────────────────────────────────────────────

    async def _ping(self, u: UnitState) -> bool:
        url = f"http://127.0.0.1:{u.host_port}/health"
        headers = {"Authorization": f"Bearer {u.auth_token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.status_code == 200
        except Exception:
            return False

    # ── Restart ───────────────────────────────────────────────────────────────

    async def _restart(self, u: UnitState) -> None:
        print(f"[health-monitor] Restarting unit {u.unit_id} ({u.unit_type})...")
        loop = asyncio.get_event_loop()

        if u.is_headless:
            await self._restart_headless(u, loop)
        else:
            await self._restart_desktop(u, loop)

    async def _restart_headless(self, u: UnitState, loop: asyncio.AbstractEventLoop) -> None:
        try:
            new_id = await loop.run_in_executor(
                None, self._docker.reset_container,
                u.unit_id, u.host_port, u.auth_token, u.volume_name,
            )
            u.container_id = new_id
            u.health_failures = 0
            self._pool.update(u)

            if await self._wait_ready(u, timeout=30.0):
                u.status = UnitStatus.ASSIGNED.value if u.assigned_agent_id else UnitStatus.IDLE.value
                self._pool.update(u)
                print(f"[health-monitor] Headless {u.unit_id} restarted → {u.status}")
            else:
                u.status = UnitStatus.UNHEALTHY.value
                self._pool.update(u)
        except Exception as exc:
            print(f"[health-monitor] Restart failed for headless {u.unit_id}: {exc} — evicting")
            await self._evict(u)

    async def _restart_desktop(self, u: UnitState, loop: asyncio.AbstractEventLoop) -> None:
        if self._vm is None:
            print(f"[health-monitor] Cannot restart desktop {u.unit_id}: VMManager unavailable")
            await self._evict(u)
            return

        try:
            await loop.run_in_executor(None, self._vm.stop_vm, u.unit_id)
            await asyncio.sleep(2)
            await loop.run_in_executor(None, self._vm.start_vm, u.unit_id)

            u.health_failures = 0
            self._pool.update(u)

            if await self._wait_ready(u, timeout=60.0):
                u.status = UnitStatus.ASSIGNED.value if u.assigned_agent_id else UnitStatus.IDLE.value
                self._pool.update(u)
                print(f"[health-monitor] Desktop {u.unit_id} restarted → {u.status}")
            else:
                u.status = UnitStatus.UNHEALTHY.value
                self._pool.update(u)
        except Exception as exc:
            print(f"[health-monitor] Restart failed for desktop {u.unit_id}: {exc} — evicting")
            await self._evict(u)

    # ── Reset (for zombie cleanup) ────────────────────────────────────────────

    async def _reset_unit(self, u: UnitState) -> None:
        if u.is_headless:
            await self._reset_headless(u)
        else:
            # For desktop, just release and mark idle
            self._pool.release(u.unit_id)

    async def _reset_headless(self, u: UnitState) -> None:
        loop = asyncio.get_event_loop()
        try:
            new_id = await loop.run_in_executor(
                None, self._docker.reset_container,
                u.unit_id, u.host_port, u.auth_token, u.volume_name,
            )
            current = self._pool.get(u.unit_id)
            if current:
                current.container_id = new_id
                self._pool.update(current)

            if await self._wait_ready(u, timeout=30.0):
                self._pool.release(u.unit_id)
            else:
                await self._evict(self._pool.get(u.unit_id) or u)
        except Exception as exc:
            print(f"[health-monitor] Reset failed for {u.unit_id}: {exc} — evicting")
            await self._evict(self._pool.get(u.unit_id) or u)

    # ── Wait ready ────────────────────────────────────────────────────────────

    async def _wait_ready(self, u: UnitState, timeout: float = 30.0) -> bool:
        url = f"http://127.0.0.1:{u.host_port}/health"
        headers = {"Authorization": f"Bearer {u.auth_token}"}
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
        return False

    # ── Evict ─────────────────────────────────────────────────────────────────

    async def _evict(self, u: UnitState) -> None:
        loop = asyncio.get_event_loop()
        unit_type = u.unit_type

        try:
            if u.is_headless:
                await loop.run_in_executor(None, self._docker.destroy_container, u.unit_id)
                if u.volume_name:
                    await loop.run_in_executor(None, self._docker.remove_volume, u.volume_name)
            elif u.is_desktop and self._vm is not None:
                await loop.run_in_executor(None, self._vm.destroy_vm, u.unit_id, u.host_port)
        except Exception as exc:
            print(f"[health-monitor] Evict error for {u.unit_id}: {exc}")
        finally:
            self._ports.release(u.host_port)
            self._pool.remove(u.unit_id)
            self._budget.release(unit_type)
