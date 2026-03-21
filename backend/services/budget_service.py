"""
BudgetService (v3): Sandbox pod-second metering and aggregate budget enforcement.

Extends the existing LLM cost tracking with:
  1. Sandbox pod-second metering: track compute time per agent session.
  2. Aggregate daily budget cap enforcement across both LLM + sandbox costs.
  3. Hard enforcement at call sites (raises BudgetExceededError).
  4. Soft warnings at 80% utilization.

Usage:
    service = BudgetService(db)
    await service.check_llm_budget(project_id, estimated_cost_usd)   # raises if over
    await service.record_sandbox_usage(agent_id, project_id, sandbox_id, seconds)
    summary = await service.get_budget_summary(project_id)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import AICTException
from backend.db.models import LLMUsageEvent, ProjectSettings
from backend.config import LLM_MODEL_PRICING
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


class BudgetExceededError(AICTException):
    """Raised when an operation would exceed the project's budget cap."""

    def __init__(self, project_id: UUID, budget_type: str, limit: float, current: float) -> None:
        self.project_id = project_id
        self.budget_type = budget_type
        self.limit = limit
        self.current = current
        super().__init__(
            f"Budget exceeded for project {project_id}: "
            f"{budget_type} current={current:.4f} limit={limit:.2f}"
        )


def _estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate LLM cost in USD using the pricing table (longest-prefix match)."""
    pricing = None
    best_match_len = -1
    for prefix, price in LLM_MODEL_PRICING.items():
        if model.startswith(prefix) and len(prefix) > best_match_len:
            pricing = price
            best_match_len = len(prefix)

    if pricing is None:
        # Unknown model — use a conservative default ($0.01/1K tokens)
        pricing = {"input": 10.0, "output": 30.0}

    cost = (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]
    return cost


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class BudgetService:
    """Per-request budget enforcement and usage metering service."""

    SANDBOX_COST_PER_HOUR_USD: float = 0.10   # $0.10/hour for GKE Autopilot compute (configurable)
    WARNING_THRESHOLD_PCT: float = 0.80        # warn at 80% utilization

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _get_settings(self, project_id: UUID) -> ProjectSettings | None:
        result = await self._db.execute(
            select(ProjectSettings).where(ProjectSettings.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def _get_rolling_llm_cost_usd(self, project_id: UUID, hours: int = 24) -> float:
        """Sum estimated LLM cost for the project in the last N hours."""
        window_start = _utcnow() - timedelta(hours=hours)
        result = await self._db.execute(
            select(LLMUsageEvent.input_tokens, LLMUsageEvent.output_tokens, LLMUsageEvent.model)
            .where(
                LLMUsageEvent.project_id == project_id,
                LLMUsageEvent.created_at >= window_start,
            )
        )
        rows = result.all()
        total = sum(_estimate_llm_cost(r.model, r.input_tokens, r.output_tokens) for r in rows)
        return total

    async def _get_rolling_sandbox_cost_usd(self, project_id: UUID, hours: int = 24) -> float:
        """Sum sandbox pod-second costs for the project in the last N hours."""
        try:
            window_start = _utcnow() - timedelta(hours=hours)
            result = await self._db.execute(
                text(
                    "SELECT COALESCE(SUM(pod_seconds), 0) FROM sandbox_usage_events "
                    "WHERE project_id = :pid AND created_at >= :start AND event_type = 'session_end'"
                ),
                {"pid": str(project_id), "start": window_start},
            )
            total_seconds: float = result.scalar_one() or 0.0
            # Convert pod-seconds to cost
            return (total_seconds / 3600.0) * self.SANDBOX_COST_PER_HOUR_USD
        except Exception as exc:
            # Table not yet migrated — log at WARNING so silent budget bypass is visible
            logger.warning(
                "BudgetService: sandbox_usage_events query failed (migration pending?): %s", exc
            )
            return 0.0

    async def check_llm_budget(
        self,
        project_id: UUID,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> None:
        """
        Check whether proceeding with an LLM call would breach the daily cost budget.

        Raises BudgetExceededError if the estimated cost would push the project over its limit.
        Logs a warning at 80% utilization.

        This is a HARD enforcement gate — call this BEFORE making the LLM API call.
        """
        ps = await self._get_settings(project_id)
        if ps is None or ps.daily_cost_budget_usd <= 0:
            return  # No budget configured — allow

        estimated_call_cost = _estimate_llm_cost(model, estimated_input_tokens, estimated_output_tokens)
        current_cost = await self._get_rolling_llm_cost_usd(project_id)
        sandbox_cost = await self._get_rolling_sandbox_cost_usd(project_id)
        total_current = current_cost + sandbox_cost
        total_projected = total_current + estimated_call_cost

        utilization = total_current / ps.daily_cost_budget_usd

        if utilization >= self.WARNING_THRESHOLD_PCT:
            logger.warning(
                "BudgetService: project %s at %.0f%% of daily budget "
                "($%.4f of $%.2f used)",
                project_id, utilization * 100, total_current, ps.daily_cost_budget_usd,
            )

        if total_projected > ps.daily_cost_budget_usd:
            raise BudgetExceededError(
                project_id=project_id,
                budget_type="daily_cost_usd",
                limit=ps.daily_cost_budget_usd,
                current=total_current,
            )

    async def record_sandbox_usage(
        self,
        agent_id: UUID,
        project_id: UUID,
        sandbox_id: str,
        pod_seconds: float,
        event_type: str = "session_end",
        user_id: UUID | None = None,
        unit_type: str = "headless",
    ) -> None:
        """
        Record sandbox compute usage for metering and billing.

        event_type: "session_end" | "heartbeat" | "reclaim_candidate"
        pod_seconds: wall-clock seconds the sandbox was actively used.
        user_id: optional — when provided, tier usage counters are updated.
        unit_type: "headless" | "desktop" — used to update the correct tier counter.
        """
        try:
            await self._db.execute(
                text(
                    "INSERT INTO sandbox_usage_events "
                    "(id, agent_id, project_id, sandbox_id, pod_seconds, event_type, created_at) "
                    "VALUES (gen_random_uuid(), :agent_id, :project_id, :sandbox_id, "
                    ":pod_seconds, :event_type, :now)"
                ),
                {
                    "agent_id": str(agent_id),
                    "project_id": str(project_id),
                    "sandbox_id": sandbox_id,
                    "pod_seconds": pod_seconds,
                    "event_type": event_type,
                    "now": _utcnow(),
                },
            )
        except Exception as exc:
            # Table not yet migrated — log at WARNING so metering gaps are visible
            logger.warning("BudgetService: sandbox usage record failed (migration pending?): %s", exc)

        # Update tier usage counters
        if user_id:
            try:
                from backend.services.tier_service import TierService
                from backend.db.models import User
                user = await self._db.get(User, user_id)
                if user:
                    tier_svc = TierService(self._db)
                    await tier_svc.record_usage(user, unit_type, int(pod_seconds))
            except Exception as tier_exc:
                logger.warning("TierService usage recording failed: %s", tier_exc)

    async def get_budget_summary(self, project_id: UUID) -> dict:
        """
        Return a summary of budget utilization for a project.

        Returns:
            {
                "daily_cost_budget_usd": 5.0,
                "llm_cost_24h": 1.23,
                "sandbox_cost_24h": 0.05,
                "total_cost_24h": 1.28,
                "utilization_pct": 25.6,
                "has_budget": True,
            }
        """
        ps = await self._get_settings(project_id)
        budget = ps.daily_cost_budget_usd if ps else 0.0
        llm_cost = await self._get_rolling_llm_cost_usd(project_id)
        sandbox_cost = await self._get_rolling_sandbox_cost_usd(project_id)
        total = llm_cost + sandbox_cost
        utilization = (total / budget * 100) if budget > 0 else 0.0

        return {
            "daily_cost_budget_usd": budget,
            "llm_cost_24h": round(llm_cost, 6),
            "sandbox_cost_24h": round(sandbox_cost, 6),
            "total_cost_24h": round(total, 6),
            "utilization_pct": round(utilization, 1),
            "has_budget": budget > 0,
        }
