"""LLM usage event data access."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LLMUsageEvent


class LLMUsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        project_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: UUID | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        request_id: str | None = None,
    ) -> LLMUsageEvent:
        event = LLMUsageEvent(
            id=uuid.uuid4(),
            project_id=project_id,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            model=model,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            request_id=request_id,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def daily_tokens_for_project(self, project_id: UUID) -> int:
        """Total tokens (input + output) used by a project today (UTC)."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(LLMUsageEvent.input_tokens + LLMUsageEvent.output_tokens), 0
                )
            ).where(
                LLMUsageEvent.project_id == project_id,
                LLMUsageEvent.created_at >= today_start,
            )
        )
        return int(result.scalar() or 0)

    async def usage_summary(
        self,
        project_id: UUID,
        limit: int = 50,
    ) -> list[dict]:
        """Last N usage events for a project, newest first."""
        result = await self.session.execute(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.project_id == project_id)
            .order_by(LLMUsageEvent.created_at.desc())
            .limit(limit)
        )
        events = list(result.scalars().all())
        return [
            {
                "id": str(e.id),
                "provider": e.provider,
                "model": e.model,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "total_tokens": e.input_tokens + e.output_tokens,
                "agent_id": str(e.agent_id) if e.agent_id else None,
                "session_id": str(e.session_id) if e.session_id else None,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]

    async def daily_rollup(self, project_id: UUID) -> dict:
        """Today's token totals and per-model breakdown."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(
                LLMUsageEvent.model,
                LLMUsageEvent.provider,
                func.sum(LLMUsageEvent.input_tokens).label("input_tokens"),
                func.sum(LLMUsageEvent.output_tokens).label("output_tokens"),
                func.count(LLMUsageEvent.id).label("calls"),
            )
            .where(
                LLMUsageEvent.project_id == project_id,
                LLMUsageEvent.created_at >= today_start,
            )
            .group_by(LLMUsageEvent.model, LLMUsageEvent.provider)
            .order_by(func.sum(LLMUsageEvent.input_tokens + LLMUsageEvent.output_tokens).desc())
        )
        rows = result.all()
        total_input = sum(r.input_tokens or 0 for r in rows)
        total_output = sum(r.output_tokens or 0 for r in rows)
        return {
            "date_utc": today_start.date().isoformat(),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "by_model": [
                {
                    "provider": r.provider,
                    "model": r.model,
                    "calls": r.calls,
                    "input_tokens": r.input_tokens or 0,
                    "output_tokens": r.output_tokens or 0,
                }
                for r in rows
            ],
        }
