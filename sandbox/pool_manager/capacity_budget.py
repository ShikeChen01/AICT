"""CapacityBudget — enforces CPU, RAM, disk, and unit-count limits.

The Grand-VM has a fixed allocable budget (CPU, RAM, disk) shared between
Docker headless containers and QEMU desktop sub-VMs. This module tracks
running totals and rejects requests that would exceed any limit.

Thread-safe: all mutations go through a threading.Lock.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import config


@dataclass(frozen=True)
class ResourceCost:
    """Resources consumed by a single unit."""

    cpu: float
    ram_gb: float
    disk_gb: float


HEADLESS_COST = ResourceCost(
    cpu=config.HEADLESS_CPU_BUDGET,
    ram_gb=config.HEADLESS_RAM_BUDGET_GB,
    disk_gb=config.HEADLESS_DISK_QUOTA_GB,
)

DESKTOP_COST = ResourceCost(
    cpu=config.DESKTOP_CPU_BUDGET,
    ram_gb=config.DESKTOP_RAM_GB,
    disk_gb=config.DESKTOP_DISK_QUOTA_GB,
)


@dataclass
class ExhaustedError(Exception):
    """Raised when a resource budget would be exceeded."""

    resource: str
    allocated: float
    budget: float
    requested: float

    def __str__(self) -> str:
        return (
            f"capacity_exhausted: {self.resource} "
            f"(allocated={self.allocated:.2f}, budget={self.budget:.2f}, "
            f"requested={self.requested:.2f})"
        )

    def to_dict(self) -> dict:
        return {
            "error": "capacity_exhausted",
            "resource": self.resource,
            "allocated": round(self.allocated, 3),
            "budget": round(self.budget, 3),
            "requested": round(self.requested, 3),
        }


@dataclass
class BudgetSnapshot:
    """Read-only snapshot of current budget utilization."""

    cpu_allocated: float
    cpu_budget: float
    ram_allocated_gb: float
    ram_budget_gb: float
    disk_allocated_gb: float
    disk_budget_gb: float
    headless_count: int
    headless_max: int
    desktop_count: int
    desktop_max: int
    total_count: int
    total_max: int

    def to_dict(self) -> dict:
        return {
            "cpu": {"allocated": round(self.cpu_allocated, 2), "budget": self.cpu_budget},
            "ram_gb": {"allocated": round(self.ram_allocated_gb, 2), "budget": self.ram_budget_gb},
            "disk_gb": {"allocated": round(self.disk_allocated_gb, 2), "budget": self.disk_budget_gb},
            "headless": {"count": self.headless_count, "max": self.headless_max},
            "desktop": {"count": self.desktop_count, "max": self.desktop_max},
            "total": {"count": self.total_count, "max": self.total_max},
            "can_add_headless": self._can_add("headless"),
            "can_add_desktop": self._can_add("desktop"),
        }

    def _can_add(self, unit_type: str) -> bool:
        cost = HEADLESS_COST if unit_type == "headless" else DESKTOP_COST
        type_count = self.headless_count if unit_type == "headless" else self.desktop_count
        type_max = self.headless_max if unit_type == "headless" else self.desktop_max
        return (
            type_count < type_max
            and self.total_count < self.total_max
            and self.cpu_allocated + cost.cpu <= self.cpu_budget + 0.001
            and self.ram_allocated_gb + cost.ram_gb <= self.ram_budget_gb + 0.001
            and self.disk_allocated_gb + cost.disk_gb <= self.disk_budget_gb + 0.001
        )


class CapacityBudget:
    """Thread-safe resource budget tracker for the Grand-VM."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cpu: float = 0.0
        self._ram_gb: float = 0.0
        self._disk_gb: float = 0.0
        self._headless: int = 0
        self._desktop: int = 0

    # ── Reserve / release ─────────────────────────────────────────────────────

    def reserve(self, unit_type: str) -> None:
        """Reserve resources for a new unit. Raises ExhaustedError on overflow."""
        cost = HEADLESS_COST if unit_type == "headless" else DESKTOP_COST
        type_limit = config.MAX_HEADLESS if unit_type == "headless" else config.MAX_DESKTOP

        with self._lock:
            type_count = self._headless if unit_type == "headless" else self._desktop

            # Check per-type count limit
            if type_count >= type_limit:
                raise ExhaustedError(
                    resource=f"{unit_type}_count",
                    allocated=float(type_count),
                    budget=float(type_limit),
                    requested=1.0,
                )

            # Check total unit limit
            total = self._headless + self._desktop
            if total >= config.MAX_TOTAL_UNITS:
                raise ExhaustedError(
                    resource="total_units",
                    allocated=float(total),
                    budget=float(config.MAX_TOTAL_UNITS),
                    requested=1.0,
                )

            # Check CPU
            if self._cpu + cost.cpu > config.BUDGET_CPU + 0.001:
                raise ExhaustedError(
                    resource="cpu",
                    allocated=self._cpu,
                    budget=config.BUDGET_CPU,
                    requested=cost.cpu,
                )

            # Check RAM
            if self._ram_gb + cost.ram_gb > config.BUDGET_RAM_GB + 0.001:
                raise ExhaustedError(
                    resource="ram",
                    allocated=self._ram_gb,
                    budget=config.BUDGET_RAM_GB,
                    requested=cost.ram_gb,
                )

            # Check Disk
            if self._disk_gb + cost.disk_gb > config.BUDGET_DISK_GB + 0.001:
                raise ExhaustedError(
                    resource="disk",
                    allocated=self._disk_gb,
                    budget=config.BUDGET_DISK_GB,
                    requested=cost.disk_gb,
                )

            # All checks passed — commit the reservation
            self._cpu += cost.cpu
            self._ram_gb += cost.ram_gb
            self._disk_gb += cost.disk_gb
            if unit_type == "headless":
                self._headless += 1
            else:
                self._desktop += 1

    def release(self, unit_type: str) -> None:
        """Release resources when a unit is destroyed."""
        cost = HEADLESS_COST if unit_type == "headless" else DESKTOP_COST

        with self._lock:
            self._cpu = max(0.0, self._cpu - cost.cpu)
            self._ram_gb = max(0.0, self._ram_gb - cost.ram_gb)
            self._disk_gb = max(0.0, self._disk_gb - cost.disk_gb)
            if unit_type == "headless":
                self._headless = max(0, self._headless - 1)
            else:
                self._desktop = max(0, self._desktop - 1)

    # ── Promotion / demotion bookkeeping ──────────────────────────────────────

    def can_promote(self) -> bool:
        """Check if there's room to swap a headless → desktop."""
        net_cpu = DESKTOP_COST.cpu - HEADLESS_COST.cpu
        net_ram = DESKTOP_COST.ram_gb - HEADLESS_COST.ram_gb
        net_disk = DESKTOP_COST.disk_gb - HEADLESS_COST.disk_gb

        with self._lock:
            return (
                self._desktop < config.MAX_DESKTOP
                and self._cpu + net_cpu <= config.BUDGET_CPU + 0.001
                and self._ram_gb + net_ram <= config.BUDGET_RAM_GB + 0.001
                and self._disk_gb + net_disk <= config.BUDGET_DISK_GB + 0.001
            )

    def promote(self) -> None:
        """Swap accounting from headless to desktop. Raises ExhaustedError."""
        net_cpu = DESKTOP_COST.cpu - HEADLESS_COST.cpu
        net_ram = DESKTOP_COST.ram_gb - HEADLESS_COST.ram_gb
        net_disk = DESKTOP_COST.disk_gb - HEADLESS_COST.disk_gb

        with self._lock:
            if self._desktop >= config.MAX_DESKTOP:
                raise ExhaustedError("desktop_count", float(self._desktop), float(config.MAX_DESKTOP), 1.0)
            if self._cpu + net_cpu > config.BUDGET_CPU + 0.001:
                raise ExhaustedError("cpu", self._cpu, config.BUDGET_CPU, net_cpu)
            if self._ram_gb + net_ram > config.BUDGET_RAM_GB + 0.001:
                raise ExhaustedError("ram", self._ram_gb, config.BUDGET_RAM_GB, net_ram)

            self._cpu += net_cpu
            self._ram_gb += net_ram
            self._disk_gb += net_disk
            self._headless -= 1
            self._desktop += 1

    def demote(self) -> None:
        """Swap accounting from desktop to headless."""
        net_cpu = DESKTOP_COST.cpu - HEADLESS_COST.cpu
        net_ram = DESKTOP_COST.ram_gb - HEADLESS_COST.ram_gb
        net_disk = DESKTOP_COST.disk_gb - HEADLESS_COST.disk_gb

        with self._lock:
            self._cpu -= net_cpu
            self._ram_gb -= net_ram
            self._disk_gb -= net_disk
            self._desktop -= 1
            self._headless += 1

    # ── Introspection ─────────────────────────────────────────────────────────

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return BudgetSnapshot(
                cpu_allocated=self._cpu,
                cpu_budget=config.BUDGET_CPU,
                ram_allocated_gb=self._ram_gb,
                ram_budget_gb=config.BUDGET_RAM_GB,
                disk_allocated_gb=self._disk_gb,
                disk_budget_gb=config.BUDGET_DISK_GB,
                headless_count=self._headless,
                headless_max=config.MAX_HEADLESS,
                desktop_count=self._desktop,
                desktop_max=config.MAX_DESKTOP,
                total_count=self._headless + self._desktop,
                total_max=config.MAX_TOTAL_UNITS,
            )

    def rebuild_from_units(self, headless: int, desktop: int) -> None:
        """Reconstruct budget counters from actual running units (startup reconciliation)."""
        with self._lock:
            self._headless = headless
            self._desktop = desktop
            self._cpu = headless * HEADLESS_COST.cpu + desktop * DESKTOP_COST.cpu
            self._ram_gb = headless * HEADLESS_COST.ram_gb + desktop * DESKTOP_COST.ram_gb
            self._disk_gb = headless * HEADLESS_COST.disk_gb + desktop * DESKTOP_COST.disk_gb
