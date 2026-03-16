"""Tests for PortAllocator — split range allocation."""

import sys
import os
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from port_allocator import PortAllocator


@pytest.fixture
def pa():
    return PortAllocator()


class TestPortAllocator:
    def test_headless_range(self, pa):
        port = pa.allocate("headless")
        assert port is not None
        assert config.HEADLESS_PORT_START <= port <= config.HEADLESS_PORT_END

    def test_desktop_range(self, pa):
        port = pa.allocate("desktop")
        assert port is not None
        assert config.DESKTOP_PORT_START <= port <= config.DESKTOP_PORT_END

    def test_sequential_allocation(self, pa):
        p1 = pa.allocate("headless")
        p2 = pa.allocate("headless")
        assert p1 != p2
        assert p1 == config.HEADLESS_PORT_START
        assert p2 == config.HEADLESS_PORT_START + 1

    def test_release_makes_port_available(self, pa):
        p1 = pa.allocate("headless")
        pa.release(p1)
        p2 = pa.allocate("headless")
        assert p2 == p1

    def test_exhaustion_returns_none(self, pa):
        """Allocate all ports in a range, then verify None is returned."""
        allocated = []
        for _ in range(config.HEADLESS_PORT_END - config.HEADLESS_PORT_START + 1):
            p = pa.allocate("headless")
            assert p is not None
            allocated.append(p)

        assert pa.allocate("headless") is None

    def test_reclaim_from_pool(self, pa):
        pa.reclaim_from_pool([30001, 30002, 30051])
        # 30001 and 30002 should be in use
        p = pa.allocate("headless")
        assert p == 30003  # Next free headless port
        # 30051 should be in use
        p = pa.allocate("desktop")
        assert p == 30052  # Next free desktop port

    def test_thread_safety(self, pa):
        ports = []
        lock = threading.Lock()

        def worker():
            for _ in range(5):
                p = pa.allocate("headless")
                if p is not None:
                    with lock:
                        ports.append(p)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All allocated ports should be unique
        assert len(ports) == len(set(ports))
