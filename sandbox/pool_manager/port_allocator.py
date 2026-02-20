"""Port allocator for mapping container port 8080 to a VM host port."""

from __future__ import annotations

import threading
from typing import Optional

from config import PORT_RANGE_END, PORT_RANGE_START


class PortAllocator:
    """Thread-safe port range allocator."""

    def __init__(
        self,
        start: int = PORT_RANGE_START,
        end: int = PORT_RANGE_END,
    ) -> None:
        self._start = start
        self._end = end
        self._used: set[int] = set()
        self._lock = threading.Lock()

    def allocate(self) -> Optional[int]:
        """Return the next free port, or None if the range is exhausted."""
        with self._lock:
            for port in range(self._start, self._end + 1):
                if port not in self._used:
                    self._used.add(port)
                    return port
        return None

    def release(self, port: int) -> None:
        """Mark a port as free."""
        with self._lock:
            self._used.discard(port)

    def reclaim_from_pool(self, used_ports: list[int]) -> None:
        """Restore allocator state after a crash recovery."""
        with self._lock:
            self._used = set(used_ports)
