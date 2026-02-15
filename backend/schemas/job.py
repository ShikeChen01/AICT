"""
Engineer job schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobResponse(BaseModel):
    """Response schema for engineer jobs."""
    id: UUID
    project_id: UUID
    task_id: UUID
    agent_id: UUID
    status: str  # pending, running, completed, failed, cancelled
    result: str | None
    error: str | None
    pr_url: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobSummary(BaseModel):
    """Summary view of a job for list views."""
    id: UUID
    task_id: UUID
    agent_id: UUID
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
