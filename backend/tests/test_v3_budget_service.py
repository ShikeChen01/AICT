"""
Tests for v3 BudgetService: cost estimation, enforcement, sandbox metering.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.services.budget_service import BudgetService, BudgetExceededError, _estimate_llm_cost


# ── Cost estimation ───────────────────────────────────────────────────────────

class TestLLMCostEstimation:

    def test_known_model_input_only(self):
        cost = _estimate_llm_cost("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 3.0) < 0.01  # $3/M input

    def test_known_model_output_only(self):
        cost = _estimate_llm_cost("claude-sonnet-4-6", input_tokens=0, output_tokens=1_000_000)
        assert abs(cost - 15.0) < 0.01  # $15/M output

    def test_known_model_mixed(self):
        cost = _estimate_llm_cost("claude-sonnet-4-6", input_tokens=500_000, output_tokens=500_000)
        expected = 0.5 * 3.0 + 0.5 * 15.0  # 1.5 + 7.5 = 9.0
        assert abs(cost - expected) < 0.01

    def test_prefix_match(self):
        # "claude-sonnet-4-6-some-suffix" should still match claude-sonnet-4-6 prefix
        cost1 = _estimate_llm_cost("claude-sonnet-4-6", 100, 100)
        cost2 = _estimate_llm_cost("claude-sonnet-4-6-preview", 100, 100)
        assert cost1 == cost2

    def test_unknown_model_uses_fallback(self):
        cost = _estimate_llm_cost("gpt-99-ultra-secret", 1_000_000, 1_000_000)
        assert cost > 0  # fallback should produce nonzero cost

    def test_zero_tokens_zero_cost(self):
        assert _estimate_llm_cost("claude-sonnet-4-6", 0, 0) == 0.0


# ── BudgetService enforcement ─────────────────────────────────────────────────

class TestBudgetServiceEnforcement:

    def _make_service_with_settings(self, budget_usd: float):
        """Create a BudgetService backed by a mock DB with the given budget."""
        from backend.db.models import ProjectSettings
        mock_db = AsyncMock()

        ps = MagicMock(spec=ProjectSettings)
        ps.daily_cost_budget_usd = budget_usd
        ps.project_id = uuid4()

        ps_result = MagicMock()
        ps_result.scalar_one_or_none.return_value = ps

        # LLM usage rows (empty — no prior usage)
        usage_result = MagicMock()
        usage_result.all.return_value = []

        mock_db.execute.side_effect = [ps_result, usage_result, MagicMock()]
        service = BudgetService(mock_db)
        return service, ps.project_id

    @pytest.mark.asyncio
    async def test_no_budget_configured_allows_all(self):
        """When daily_cost_budget_usd=0, all calls are allowed."""
        from backend.db.models import ProjectSettings
        mock_db = AsyncMock()
        ps = MagicMock(spec=ProjectSettings)
        ps.daily_cost_budget_usd = 0.0
        result = MagicMock()
        result.scalar_one_or_none.return_value = ps
        mock_db.execute.return_value = result

        service = BudgetService(mock_db)
        project_id = uuid4()
        # Should NOT raise
        await service.check_llm_budget(project_id, "claude-sonnet-4-6", 100, 100)

    @pytest.mark.asyncio
    async def test_no_settings_allows_all(self):
        """When no ProjectSettings exist, all calls are allowed."""
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        service = BudgetService(mock_db)
        # Should NOT raise
        await service.check_llm_budget(uuid4(), "claude-sonnet-4-6", 100, 100)

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self):
        """When projected cost exceeds budget, BudgetExceededError is raised."""
        from backend.db.models import ProjectSettings
        mock_db = AsyncMock()

        project_id = uuid4()
        ps = MagicMock(spec=ProjectSettings)
        ps.daily_cost_budget_usd = 0.001  # very low budget

        ps_result = MagicMock()
        ps_result.scalar_one_or_none.return_value = ps

        # No prior usage
        usage_result = MagicMock()
        usage_result.all.return_value = []

        # Sandbox cost: 0
        mock_db.execute.side_effect = [
            ps_result,
            usage_result,
            MagicMock(scalar_one=MagicMock(return_value=0.0)),
        ]

        service = BudgetService(mock_db)
        with pytest.raises(BudgetExceededError) as exc_info:
            # 1M tokens of claude-sonnet-4-6 = ~$18 — way over $0.001 limit
            await service.check_llm_budget(project_id, "claude-sonnet-4-6", 500_000, 500_000)

        assert exc_info.value.project_id == project_id
        assert exc_info.value.budget_type == "daily_cost_usd"


# ── Budget summary ────────────────────────────────────────────────────────────

class TestBudgetSummary:

    @pytest.mark.asyncio
    async def test_get_budget_summary_structure(self):
        from backend.db.models import ProjectSettings
        mock_db = AsyncMock()
        project_id = uuid4()

        ps = MagicMock(spec=ProjectSettings)
        ps.daily_cost_budget_usd = 10.0
        ps_result = MagicMock()
        ps_result.scalar_one_or_none.return_value = ps

        usage_result = MagicMock()
        usage_result.all.return_value = []

        # Sandbox query: exception (table not migrated)
        def side_effects(*args, **kwargs):
            call_count = side_effects.count
            side_effects.count += 1
            if call_count == 0:
                return ps_result
            elif call_count == 1:
                return usage_result
            else:
                raise Exception("no table")
        side_effects.count = 0
        mock_db.execute.side_effect = side_effects

        service = BudgetService(mock_db)
        summary = await service.get_budget_summary(project_id)

        assert "daily_cost_budget_usd" in summary
        assert "llm_cost_24h" in summary
        assert "sandbox_cost_24h" in summary
        assert "total_cost_24h" in summary
        assert "utilization_pct" in summary
        assert "has_budget" in summary
        assert summary["has_budget"] is True
        assert summary["daily_cost_budget_usd"] == 10.0
