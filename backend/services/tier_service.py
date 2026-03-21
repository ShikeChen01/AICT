"""
TierService — sandbox hour enforcement by membership tier.

All sandbox usage limits are enforced here. Projects, agents, and LLM
usage are unrestricted on all tiers (users bring their own API keys).
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import TierLimitError
from backend.db.models import Subscription, UsagePeriod, User
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

TIER_LIMITS: dict[str, dict] = {
    "free": {
        "headless_seconds": 15 * 3600,
        "desktop_seconds": 15 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "individual": {
        "headless_seconds": 200 * 3600,
        "desktop_seconds": 200 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "team": {
        "headless_seconds": 1000 * 3600,
        "desktop_seconds": 1000 * 3600,
        "max_team_members": 3,
        "snapshots": False,
    },
}


def _get_limits(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TierService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def check_can_start_sandbox(self, user: User, unit_type: str) -> None:
        """Raise TierLimitError if user has exhausted sandbox hours for this type."""
        # Always block past-due users regardless of enforcement flag
        result = await self._db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = result.scalar_one_or_none()
        if sub and sub.status == "past_due":
            raise TierLimitError(
                message="Your payment is past due. Please update your payment method to continue using sandboxes.",
                current_tier=user.tier,
            )

        if not settings.tier_enforcement_enabled:
            return

        limits = _get_limits(user.tier)
        limit_key = f"{unit_type}_seconds"
        limit_seconds = limits.get(limit_key, 0)

        period = await self._get_or_create_period(user)
        used = getattr(period, f"{unit_type}_seconds", 0)

        if used >= limit_seconds:
            hours_used = used / 3600
            hours_limit = limit_seconds / 3600
            tier = user.tier
            raise TierLimitError(
                message=(
                    f"You've used {hours_used:.0f} of {hours_limit:.0f} "
                    f"{tier} {unit_type} hours this month. "
                    + (
                        f"Upgrade to Individual for {TIER_LIMITS['individual'][limit_key] // 3600} hours."
                        if tier == "free"
                        else "Usage resets next billing cycle."
                    )
                ),
                current_tier=tier,
            )

    async def get_remaining_seconds(self, user: User, unit_type: str) -> int:
        limits = _get_limits(user.tier)
        limit_seconds = limits.get(f"{unit_type}_seconds", 0)
        period = await self._get_or_create_period(user)
        used = getattr(period, f"{unit_type}_seconds", 0)
        return max(0, limit_seconds - used)

    async def record_usage(self, user: User, unit_type: str, seconds: int) -> None:
        period = await self._get_or_create_period(user)
        col = f"{unit_type}_seconds"
        current = getattr(period, col, 0)
        setattr(period, col, current + seconds)
        await self._db.commit()
        await self._db.refresh(period)

    async def check_can_invite_member(self, user: User, current_count: int) -> None:
        if not settings.tier_enforcement_enabled:
            return
        limits = _get_limits(user.tier)
        max_members = limits["max_team_members"]
        if current_count >= max_members:
            raise TierLimitError(
                message=f"{user.tier.title()} tier allows {max_members} team member(s). Upgrade for more.",
                current_tier=user.tier,
            )

    async def get_usage_summary(self, user: User) -> dict:
        limits = _get_limits(user.tier)
        period = await self._get_or_create_period(user)
        return {
            "tier": user.tier,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "headless_seconds_used": period.headless_seconds,
            "headless_seconds_included": limits["headless_seconds"],
            "desktop_seconds_used": period.desktop_seconds,
            "desktop_seconds_included": limits["desktop_seconds"],
        }

    async def _get_or_create_period(self, user: User) -> UsagePeriod:
        period = await self._get_current_period(user)
        if period:
            return period
        return await self._ensure_usage_period(user)

    async def _get_current_period(self, user: User) -> UsagePeriod | None:
        now = _now()
        result = await self._db.execute(
            select(UsagePeriod).where(
                UsagePeriod.user_id == user.id,
                UsagePeriod.period_start <= now,
                UsagePeriod.period_end > now,
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_usage_period(self, user: User) -> UsagePeriod:
        existing = await self._get_current_period(user)
        if existing:
            return existing
        now = _now()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)
        period = UsagePeriod(
            id=uuid_mod.uuid4(),
            user_id=user.id,
            period_start=period_start,
            period_end=period_end,
        )
        self._db.add(period)
        await self._db.commit()
        await self._db.refresh(period)
        return period
