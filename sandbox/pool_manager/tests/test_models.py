"""Tests for models.py — UnitState, PoolState, and persistence."""

import json
import sys
import os
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import PoolState, UnitState, UnitStatus, UnitType


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_state_file(tmp_path):
    return str(tmp_path / "test_state.json")


@pytest.fixture
def pool(tmp_state_file):
    return PoolState(tmp_state_file)


def _make_unit(
    unit_id: str = "test-001",
    unit_type: str = "headless",
    host_port: int = 30001,
    status: str = "idle",
    persistent: bool = False,
    agent_id: str | None = None,
) -> UnitState:
    return UnitState(
        unit_id=unit_id,
        unit_type=unit_type,
        host_port=host_port,
        auth_token="tok-abc",
        status=status,
        persistent=persistent,
        assigned_agent_id=agent_id,
    )


# ── UnitState ────────────────────────────────────────────────────────────────


class TestUnitState:
    def test_is_headless(self):
        u = _make_unit(unit_type="headless")
        assert u.is_headless is True
        assert u.is_desktop is False

    def test_is_desktop(self):
        u = _make_unit(unit_type="desktop")
        assert u.is_headless is False
        assert u.is_desktop is True

    def test_touch_updates_timestamp(self):
        u = _make_unit()
        old = u.last_used_at
        time.sleep(0.01)
        u.touch()
        assert u.last_used_at != old

    def test_touch_command(self):
        u = _make_unit()
        assert u.last_command_at is None
        u.touch_command()
        assert u.last_command_at is not None

    def test_idle_seconds(self):
        u = _make_unit()
        assert u.idle_seconds() >= 0
        assert u.idle_seconds() < 5  # Just created

    def test_command_idle_seconds_fallback(self):
        u = _make_unit()
        # When no command has ever been run, falls back to idle_seconds
        assert u.command_idle_seconds() >= 0

    def test_to_dict_roundtrip(self):
        u = _make_unit(agent_id="agent-99")
        d = u.to_dict()
        u2 = UnitState.from_dict(d)
        assert u2.unit_id == u.unit_id
        assert u2.unit_type == u.unit_type
        assert u2.assigned_agent_id == "agent-99"

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "unit_id": "x",
            "unit_type": "headless",
            "host_port": 30001,
            "auth_token": "t",
            "status": "idle",
            "unknown_field": "should_be_ignored",
        }
        u = UnitState.from_dict(d)
        assert u.unit_id == "x"
        assert not hasattr(u, "unknown_field")


# ── PoolState CRUD ───────────────────────────────────────────────────────────


class TestPoolStateCRUD:
    def test_add_and_get(self, pool):
        u = _make_unit()
        pool.add(u)
        assert pool.get("test-001") is not None
        assert pool.get("test-001").unit_id == "test-001"

    def test_remove(self, pool):
        u = _make_unit()
        pool.add(u)
        pool.remove("test-001")
        assert pool.get("test-001") is None

    def test_update(self, pool):
        u = _make_unit()
        pool.add(u)
        u.status = "assigned"
        pool.update(u)
        assert pool.get("test-001").status == "assigned"

    def test_all(self, pool):
        pool.add(_make_unit("u1"))
        pool.add(_make_unit("u2"))
        assert len(pool.all()) == 2

    def test_all_by_type(self, pool):
        pool.add(_make_unit("h1", unit_type="headless"))
        pool.add(_make_unit("d1", unit_type="desktop", host_port=30051))
        assert len(pool.all_by_type("headless")) == 1
        assert len(pool.all_by_type("desktop")) == 1


# ── PoolState assignment ─────────────────────────────────────────────────────


class TestPoolStateAssignment:
    def test_assign(self, pool):
        pool.add(_make_unit())
        pool.assign("test-001", "agent-42")
        u = pool.get("test-001")
        assert u.assigned_agent_id == "agent-42"
        assert u.status == UnitStatus.ASSIGNED.value

    def test_get_by_agent(self, pool):
        pool.add(_make_unit())
        pool.assign("test-001", "agent-42")
        u = pool.get_by_agent("agent-42")
        assert u is not None
        assert u.unit_id == "test-001"

    def test_release(self, pool):
        pool.add(_make_unit())
        pool.assign("test-001", "agent-42")
        pool.release("test-001")
        u = pool.get("test-001")
        assert u.assigned_agent_id is None
        assert u.status == UnitStatus.IDLE.value
        assert pool.get_by_agent("agent-42") is None

    def test_mark_resetting(self, pool):
        pool.add(_make_unit())
        pool.assign("test-001", "agent-42")
        pool.mark_resetting("test-001")
        u = pool.get("test-001")
        assert u.status == UnitStatus.RESETTING.value
        assert u.assigned_agent_id is None


# ── PoolState queries ────────────────────────────────────────────────────────


class TestPoolStateQueries:
    def test_idle(self, pool):
        pool.add(_make_unit("h1", status="idle"))
        pool.add(_make_unit("h2", status="assigned", host_port=30002))
        assert len(pool.idle()) == 1
        assert pool.idle()[0].unit_id == "h1"

    def test_idle_filter_by_type(self, pool):
        pool.add(_make_unit("h1", unit_type="headless", status="idle"))
        pool.add(_make_unit("d1", unit_type="desktop", status="idle", host_port=30051))
        assert len(pool.idle("headless")) == 1
        assert len(pool.idle("desktop")) == 1

    def test_active_count(self, pool):
        pool.add(_make_unit("h1", status="idle"))
        pool.add(_make_unit("h2", status="unhealthy", host_port=30002))
        assert pool.active_count() == 1  # unhealthy excluded

    def test_headless_count(self, pool):
        pool.add(_make_unit("h1", unit_type="headless"))
        pool.add(_make_unit("d1", unit_type="desktop", host_port=30051))
        assert pool.headless_count() == 1
        assert pool.desktop_count() == 1


# ── PoolState persistence ───────────────────────────────────────────────────


class TestPoolStatePersistence:
    def test_save_and_reload(self, tmp_state_file):
        pool1 = PoolState(tmp_state_file)
        pool1.add(_make_unit("persist-1", agent_id="a1"))
        pool1.assign("persist-1", "a1")

        pool2 = PoolState(tmp_state_file)
        u = pool2.get("persist-1")
        assert u is not None
        assert u.assigned_agent_id == "a1"
        assert pool2.get_by_agent("a1") is not None

    def test_v3_backward_compat_load(self, tmp_state_file):
        """Verify that v3 'sandboxes' key is migrated to 'units'."""
        v3_data = {
            "sandboxes": [
                {
                    "sandbox_id": "legacy-001",
                    "host_port": 30001,
                    "auth_token": "tok",
                    "status": "idle",
                }
            ],
            "agent_map": {},
        }
        with open(tmp_state_file, "w") as f:
            json.dump(v3_data, f)

        pool = PoolState(tmp_state_file)
        u = pool.get("legacy-001")
        assert u is not None
        assert u.unit_type == "headless"  # Default for migrated v3 units


# ── SandboxState backward compat alias ───────────────────────────────────────


class TestBackwardCompat:
    def test_sandbox_state_alias(self):
        from models import SandboxState
        assert SandboxState is UnitState
