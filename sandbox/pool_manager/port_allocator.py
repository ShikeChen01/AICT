"""Port allocator — v4 split ranges for headless and desktop units.

Headless containers: 30001–30050
Desktop sub-VMs:     30051–30100
"""

from __future__ import annotations

import threading
from typing import Optional

import config


class PortAllocator:
    """Thread-safe port range allocator with per-type pools."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._used: set[int] = set()

    def allocate(self, unit_type: str = "headless") -> Optional[int]:
        """Return the next free port for the given unit type."""
        if unit_type == "desktop":
            start, end = config.DESKTOP_PORT_START, config.DESKTOP_PORT_END
        else:
            start, end = config.HEADLESS_PORT_START, config.HEADLESS_PORT_END

        with self._lock:
            for port in range(start, end + 1):
                if port not in self._used:
                    self._used.add(port)
                    return port
        return None

    def release(self, port: int) -> None:
        with self._lock:
            self._used.discard(port)

    def reclaim_from_pool(self, used_ports: list[int]) -> None:
        """Restore allocator state after a crash recovery."""
        with self._lock:
            self._used = set(used_ports)
