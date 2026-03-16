"""Tests for watchdog.py — state management and health check logic."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from watchdog import WatchdogState, _now_iso


class TestWatchdogState:
    def test_initial_state(self):
        state = WatchdogState()
        assert state.status == "starting"
        assert state.consecutive_failures == 0
        assert state.total_restarts == 0
        assert state.alert_active is False
        assert state.process is None

    def test_to_dict(self):
        state = WatchdogState()
        d = state.to_dict()
        assert "status" in d
        assert "pool_manager_pid" in d
        assert "pool_manager_alive" in d
        assert d["pool_manager_pid"] is None
        assert d["pool_manager_alive"] is False

    def test_now_iso_format(self):
        ts = _now_iso()
        assert "T" in ts
        assert "+" in ts or "Z" in ts or ts.endswith("+00:00")
