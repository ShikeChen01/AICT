"""
v3 Budget API — sandbox metering and aggregate cost enforcement.

Endpoints:
  GET  /budget/{project_id}                Budget summary (cost, utilization, limits)
  POST /budget/{project_id}/sandbox-usage  Record sandbox pod-seconds for a session
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import User
from backend.db.session import get_db
from backend.services.budget_service import BudgetService
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/budget", tags=["budget"])


class BudgetSummaryResponse(BaseModel):
    project_id: str
    daily_cost_budget_usd: float
    llm_cost_24h: float
    sandbox_cost_24h: float
    total_cost_24h: float
    utilization_pct: float
    has_budget: bool


class SandboxUsageRecord(BaseModel):
    agent_id: UUID
    sandbox_id: str
    pod_seconds: float = Field(gt=0, description="Wall-clock seconds of sandbox usage")
    event_type: str = Field(default="session_end", description="session_end | heartbeat")


@router.get("/{project_id}", response_model=BudgetSummaryResponse)
async def get_budget_summary(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return budget utilization summary for a project."""
    await require_project_access(db, project_id, current_user.id)
    service = BudgetService(db)
    summary = await service.get_budget_summary(project_id)
    return BudgetSummaryResponse(project_id=str(project_id), **summary)


@router.post("/{project_id}/sandbox-usage", status_code=status.HTTP_204_NO_CONTENT)
async def record_sandbox_usage(
    project_id: UUID,
    body: SandboxUsageRecord,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record sandbox compute usage for metering (called at session end or on heartbeat).

    The sandbox orchestrator or agent worker should call this when a sandbox session ends.
    """
    await require_project_access(db, project_id, current_user.id)
    service = BudgetService(db)
    await service.record_sandbox_usage(
        agent_id=body.agent_id,
        project_id=project_id,
        sandbox_id=body.sandbox_id,
        pod_seconds=body.pod_seconds,
        event_type=body.event_type,
    )
    await db.commit()
