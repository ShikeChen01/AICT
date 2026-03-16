"""Tests for CapacityBudget — resource accounting and limit enforcement."""

import sys
import os
import threading

import pytest

# Ensure pool_manager is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from capacity_budget import (
    CapacityBudget,
    ExhaustedError,
    BudgetSnapshot,
    HEADLESS_COST,
    DESKTOP_COST,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def budget():
    return CapacityBudget()


# ── Basic reserve / release ──────────────────────────────────────────────────


class TestReserveRelease:
    def test_reserve_headless(self, budget):
        budget.reserve("headless")
        snap = budget.snapshot()
        assert snap.headless_count == 1
        assert snap.desktop_count == 0
        assert abs(snap.cpu_allocated - HEADLESS_COST.cpu) < 0.001

    def test_reserve_desktop(self, budget):
        budget.reserve("desktop")
        snap = budget.snapshot()
        assert snap.desktop_count == 1
        assert snap.headless_count == 0
        assert abs(snap.cpu_allocated - DESKTOP_COST.cpu) < 0.001

    def test_release_headless(self, budget):
        budget.reserve("headless")
        budget.release("headless")
        snap = budget.snapshot()
        assert snap.headless_count == 0
        assert abs(snap.cpu_allocated) < 0.001

    def test_release_desktop(self, budget):
        budget.reserve("desktop")
        budget.release("desktop")
        snap = budget.snapshot()
        assert snap.desktop_count == 0
        assert abs(snap.cpu_allocated) < 0.001

    def test_release_never_goes_negative(self, budget):
        budget.release("headless")
        snap = budget.snapshot()
        assert snap.headless_count == 0
        assert snap.cpu_allocated >= 0


# ── Capacity limits ──────────────────────────────────────────────────────────


class TestCapacityLimits:
    def test_headless_count_limit(self, budget):
        for _ in range(config.MAX_HEADLESS):
            budget.reserve("headless")

        with pytest.raises(ExhaustedError) as exc_info:
            budget.reserve("headless")
        assert exc_info.value.resource == "headless_count"

    def test_desktop_count_limit(self, budget):
        for _ in range(config.MAX_DESKTOP):
            budget.reserve("desktop")

        with pytest.raises(ExhaustedError) as exc_info:
            budget.reserve("desktop")
        assert exc_info.value.resource == "desktop_count"

    def test_total_unit_limit(self, budget):
        """Fill all headless + desktop slots, verify total cap kicks in."""
        for _ in range(config.MAX_HEADLESS):
            budget.reserve("headless")
        for _ in range(config.MAX_DESKTOP):
            budget.reserve("desktop")

        snap = budget.snapshot()
        assert snap.total_count == config.MAX_HEADLESS + config.MAX_DESKTOP

    def test_cpu_limit(self, budget):
        """CPU should be the binding constraint at full headless + desktop."""
        # At 35 headless (3.5 CPU) + 3 desktop (3.0 CPU) = 6.5 / 6.5 CPU
        for _ in range(config.MAX_HEADLESS):
            budget.reserve("headless")
        for _ in range(config.MAX_DESKTOP):
            budget.reserve("desktop")

        snap = budget.snapshot()
        assert abs(snap.cpu_allocated - config.BUDGET_CPU) < 0.01

    def test_exhausted_error_serialization(self, budget):
        err = ExhaustedError("cpu", 6.4, 6.5, 1.0)
        d = err.to_dict()
        assert d["error"] == "capacity_exhausted"
        assert d["resource"] == "cpu"
        assert "allocated" in d


# ── Promote / Demote ─────────────────────────────────────────────────────────


class TestPromoteDemote:
    def test_promote_adjusts_counts(self, budget):
        budget.reserve("headless")
        budget.promote()
        snap = budget.snapshot()
        assert snap.headless_count == 0
        assert snap.desktop_count == 1

    def test_promote_adjusts_resources(self, budget):
        budget.reserve("headless")
        snap_before = budget.snapshot()
        budget.promote()
        snap_after = budget.snapshot()
        # CPU should increase by (desktop_cost - headless_cost)
        expected_delta = DESKTOP_COST.cpu - HEADLESS_COST.cpu
        assert abs(snap_after.cpu_allocated - snap_before.cpu_allocated - expected_delta) < 0.001

    def test_demote_adjusts_counts(self, budget):
        budget.reserve("desktop")
        budget.demote()
        snap = budget.snapshot()
        assert snap.headless_count == 1
        assert snap.desktop_count == 0

    def test_can_promote_false_at_desktop_limit(self, budget):
        for _ in range(config.MAX_DESKTOP):
            budget.reserve("desktop")
        budget.reserve("headless")
        assert budget.can_promote() is False

    def test_promote_at_limit_raises(self, budget):
        for _ in range(config.MAX_DESKTOP):
            budget.reserve("desktop")
        budget.reserve("headless")
        with pytest.raises(ExhaustedError):
            budget.promote()


# ── Snapshot ─────────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_empty_snapshot(self, budget):
        snap = budget.snapshot()
        assert snap.headless_count == 0
        assert snap.desktop_count == 0
        assert snap.total_count == 0
        d = snap.to_dict()
        assert d["can_add_headless"] is True
        assert d["can_add_desktop"] is True

    def test_snapshot_to_dict(self, budget):
        budget.reserve("headless")
        d = budget.snapshot().to_dict()
        assert "cpu" in d
        assert "ram_gb" in d
        assert "headless" in d
        assert "can_add_headless" in d
        assert d["headless"]["count"] == 1


# ── Rebuild from units ───────────────────────────────────────────────────────


class TestRebuild:
    def test_rebuild_sets_correct_totals(self, budget):
        budget.rebuild_from_units(headless=10, desktop=2)
        snap = budget.snapshot()
        assert snap.headless_count == 10
        assert snap.desktop_count == 2
        expected_cpu = 10 * HEADLESS_COST.cpu + 2 * DESKTOP_COST.cpu
        assert abs(snap.cpu_allocated - expected_cpu) < 0.001


# ── Thread safety ────────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_reserves(self, budget):
        """Hammer reserve/release from multiple threads — no crashes."""
        errors = []

        def worker():
            try:
                for _ in range(5):
                    budget.reserve("headless")
                    budget.release("headless")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        snap = budget.snapshot()
        assert snap.headless_count == 0
