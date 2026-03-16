"""Pool manager data models — v4 hybrid (headless + desktop units).

Backward-compatible: v3 SandboxState is preserved as a type alias.
The primary model is now UnitState, which tracks both Docker containers
and QEMU sub-VMs behind a unified interface.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UnitType(str, Enum):
    HEADLESS = "headless"
    DESKTOP = "desktop"


class UnitStatus(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    RESETTING = "resetting"
    UNHEALTHY = "unhealthy"
    PROMOTING = "promoting"
    DEMOTING = "demoting"


@dataclass
class UnitState:
    """Represents a single compute unit — either a Docker container or a QEMU sub-VM."""

    unit_id: str
    unit_type: str  # "headless" | "desktop"
    host_port: int
    auth_token: str
    status: str  # UnitStatus values
    persistent: bool = False

    # Docker-specific
    container_id: Optional[str] = None
    volume_name: Optional[str] = None

    # QEMU-specific
    domain_name: Optional[str] = None
    vm_ip: Optional[str] = None

    # Assignment
    assigned_agent_id: Optional[str] = None

    # Timestamps
    created_at: str = field(default_factory=lambda: _now().isoformat())
    last_used_at: str = field(default_factory=lambda: _now().isoformat())
    last_command_at: Optional[str] = None

    # Health
    health_failures: int = 0

    @property
    def is_headless(self) -> bool:
        return self.unit_type == UnitType.HEADLESS.value

    @property
    def is_desktop(self) -> bool:
        return self.unit_type == UnitType.DESKTOP.value

    def touch(self) -> None:
        self.last_used_at = _now().isoformat()

    def touch_command(self) -> None:
        """Record that a command was routed to this unit."""
        now = _now().isoformat()
        self.last_command_at = now
        self.last_used_at = now

    def idle_seconds(self) -> float:
        last = datetime.fromisoformat(self.last_used_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (_now() - last).total_seconds()

    def command_idle_seconds(self) -> float:
        """Seconds since last command was routed to this unit."""
        if self.last_command_at is None:
            return self.idle_seconds()
        last = datetime.fromisoformat(self.last_command_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (_now() - last).total_seconds()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UnitState":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)


# ── Backward compatibility ────────────────────────────────────────────────────
SandboxState = UnitState


class PoolState:
    """In-memory pool of unit states with JSON persistence.

    v4: Tracks both headless (Docker) and desktop (QEMU) units in a single
    unified state store.
    """

    def __init__(self, state_file: str) -> None:
        self._file = Path(state_file)
        self._units: dict[str, UnitState] = {}
        self._agent_map: dict[str, str] = {}  # agent_id → unit_id
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text())

            for d in data.get("units", []):
                u = UnitState.from_dict(d)
                self._units[u.unit_id] = u

            # v3 backward compat: "sandboxes" key → migrate to units
            for d in data.get("sandboxes", []):
                sid = d.get("sandbox_id") or d.get("unit_id")
                if sid and sid not in self._units:
                    d.setdefault("unit_id", sid)
                    d.setdefault("unit_type", "headless")
                    d.pop("sandbox_id", None)
                    u = UnitState.from_dict(d)
                    self._units[u.unit_id] = u

            for agent_id, unit_id in data.get("agent_map", {}).items():
                self._agent_map[agent_id] = unit_id

        except Exception as exc:
            print(f"[pool] WARNING: could not load state: {exc}")

    def save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "units": [u.to_dict() for u in self._units.values()],
            "agent_map": dict(self._agent_map),
        }
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(self._file)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, u: UnitState) -> None:
        self._units[u.unit_id] = u
        self.save()

    def remove(self, unit_id: str) -> None:
        u = self._units.pop(unit_id, None)
        if u and u.assigned_agent_id:
            self._agent_map.pop(u.assigned_agent_id, None)
        self.save()

    def get(self, unit_id: str) -> Optional[UnitState]:
        return self._units.get(unit_id)

    def update(self, u: UnitState) -> None:
        self._units[u.unit_id] = u
        self.save()

    def get_by_agent(self, agent_id: str) -> Optional[UnitState]:
        uid = self._agent_map.get(agent_id)
        return self._units.get(uid) if uid else None

    def assign(self, unit_id: str, agent_id: str) -> None:
        u = self._units[unit_id]
        u.assigned_agent_id = agent_id
        u.status = UnitStatus.ASSIGNED.value
        u.touch()
        self._agent_map[agent_id] = unit_id
        self.save()

    def release(self, unit_id: str) -> None:
        u = self._units.get(unit_id)
        if u:
            if u.assigned_agent_id:
                self._agent_map.pop(u.assigned_agent_id, None)
            u.assigned_agent_id = None
            u.status = UnitStatus.IDLE.value
            u.health_failures = 0
            u.touch()
        self.save()

    def mark_resetting(self, unit_id: str) -> None:
        u = self._units.get(unit_id)
        if u:
            if u.assigned_agent_id:
                self._agent_map.pop(u.assigned_agent_id, None)
            u.assigned_agent_id = None
            u.status = UnitStatus.RESETTING.value
            u.health_failures = 0
            u.touch()
        self.save()

    # ── Queries ───────────────────────────────────────────────────────────────

    def all(self) -> list[UnitState]:
        return list(self._units.values())

    def all_by_type(self, unit_type: str) -> list[UnitState]:
        return [u for u in self._units.values() if u.unit_type == unit_type]

    def idle(self, unit_type: str | None = None) -> list[UnitState]:
        return [
            u for u in self._units.values()
            if u.status == UnitStatus.IDLE.value
            and (unit_type is None or u.unit_type == unit_type)
        ]

    def active_count(self, unit_type: str | None = None) -> int:
        return sum(
            1
            for u in self._units.values()
            if u.status != UnitStatus.UNHEALTHY.value
            and (unit_type is None or u.unit_type == unit_type)
        )

    def headless_count(self) -> int:
        return self.active_count(UnitType.HEADLESS.value)

    def desktop_count(self) -> int:
        return self.active_count(UnitType.DESKTOP.value)
