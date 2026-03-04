"""Pool manager data models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SandboxState:
    sandbox_id: str
    container_id: str
    host_port: int
    volume_name: str
    auth_token: str
    status: str  # "idle" | "assigned" | "resetting" | "unhealthy"
    persistent: bool = False
    assigned_agent_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: _now().isoformat())
    last_used_at: str = field(default_factory=lambda: _now().isoformat())
    health_failures: int = 0

    def touch(self) -> None:
        self.last_used_at = _now().isoformat()

    def idle_seconds(self) -> float:
        last = datetime.fromisoformat(self.last_used_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (_now() - last).total_seconds()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SandboxState":
        return cls(**d)


class PoolState:
    """In-memory pool of sandbox states with JSON persistence."""

    def __init__(self, state_file: str) -> None:
        self._file = Path(state_file)
        self._sandboxes: dict[str, SandboxState] = {}
        self._agent_map: dict[str, str] = {}  # agent_id → sandbox_id
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text())
            for d in data.get("sandboxes", []):
                s = SandboxState.from_dict(d)
                self._sandboxes[s.sandbox_id] = s
            for agent_id, sandbox_id in data.get("agent_map", {}).items():
                self._agent_map[agent_id] = sandbox_id
        except Exception as exc:
            print(f"[pool] WARNING: could not load state: {exc}")

    def save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sandboxes": [s.to_dict() for s in self._sandboxes.values()],
            "agent_map": dict(self._agent_map),
        }
        self._file.write_text(json.dumps(data, indent=2))

    def add(self, s: SandboxState) -> None:
        self._sandboxes[s.sandbox_id] = s
        self.save()

    def remove(self, sandbox_id: str) -> None:
        s = self._sandboxes.pop(sandbox_id, None)
        if s and s.assigned_agent_id:
            self._agent_map.pop(s.assigned_agent_id, None)
        self.save()

    def get(self, sandbox_id: str) -> Optional[SandboxState]:
        return self._sandboxes.get(sandbox_id)

    def get_by_agent(self, agent_id: str) -> Optional[SandboxState]:
        sid = self._agent_map.get(agent_id)
        return self._sandboxes.get(sid) if sid else None

    def assign(self, sandbox_id: str, agent_id: str) -> None:
        s = self._sandboxes[sandbox_id]
        s.assigned_agent_id = agent_id
        s.status = "assigned"
        s.touch()
        self._agent_map[agent_id] = sandbox_id
        self.save()

    def release(self, sandbox_id: str) -> None:
        s = self._sandboxes.get(sandbox_id)
        if s:
            if s.assigned_agent_id:
                self._agent_map.pop(s.assigned_agent_id, None)
            s.assigned_agent_id = None
            s.status = "idle"
            s.health_failures = 0
            s.touch()
        self.save()

    def all(self) -> list[SandboxState]:
        return list(self._sandboxes.values())

    def idle(self) -> list[SandboxState]:
        return [s for s in self._sandboxes.values() if s.status == "idle"]

    def mark_resetting(self, sandbox_id: str) -> None:
        """
        Transition a sandbox from any state to "resetting".

        Clears the agent assignment immediately so the agent_map no longer
        references this sandbox, but keeps the entry in _sandboxes so the
        slot is still counted by active_count() while the Docker reset runs.
        """
        s = self._sandboxes.get(sandbox_id)
        if s:
            if s.assigned_agent_id:
                self._agent_map.pop(s.assigned_agent_id, None)
            s.assigned_agent_id = None
            s.status = "resetting"
            s.health_failures = 0
            s.touch()
        self.save()

    def active_count(self) -> int:
        # "unhealthy" containers are being evicted/restarted by health monitor;
        # exclude them from the capacity check so fresh slots can be created.
        # "resetting" containers are temporarily between destroy and recreate but
        # still occupy the Docker resource budget, so we count them.
        return sum(1 for s in self._sandboxes.values() if s.status != "unhealthy")

    def update(self, s: SandboxState) -> None:
        self._sandboxes[s.sandbox_id] = s
        self.save()
