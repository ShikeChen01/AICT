"""Internal sandbox execute endpoint (VM-backed)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.auth import verify_agent_request
from backend.db.models import Agent
from backend.db.session import get_db
from backend.services.sandbox_service import SandboxService

router = APIRouter(tags=["internal-sandbox"])


class ExecuteRequest(BaseModel):
    agent_id: uuid.UUID
    command: str = Field(..., min_length=1)
    timeout: int = Field(120, ge=1, le=300)


@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != uuid.UUID(auth_agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")

    result = await db.execute(
        select(Agent).options(selectinload(Agent.sandbox), selectinload(Agent.desktop)).where(Agent.id == body.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = SandboxService()

    # v4.1 (D1): Agent must have an assigned sandbox. Acquire one if needed,
    # but only headless — desktops require user action.
    sandbox = await svc.acquire_sandbox_for_agent(db, agent)
    shell_result = await svc.execute_command(sandbox, body.command, body.timeout)
    await db.commit()

    return {
        "output": shell_result.stdout,
        "exit_code": shell_result.exit_code,
        "sandbox_id": str(sandbox.id),
    }
