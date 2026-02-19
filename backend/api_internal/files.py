"""Internal sandbox execute endpoint."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import verify_agent_request
from backend.db.models import Agent
from backend.db.session import get_db
from backend.services.e2b_service import E2BService, LOCAL_FALLBACK_SANDBOX_ERROR

router = APIRouter(tags=["internal-sandbox"])

try:
    from e2b import AsyncSandbox
except Exception:  # pragma: no cover - optional dependency
    AsyncSandbox = None


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

    result = await db.execute(select(Agent).where(Agent.id == body.agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.sandbox_id:
        svc = E2BService()
        await svc.create_sandbox(db, agent, persistent=bool(agent.sandbox_persist))
        await db.commit()

    if E2BService._is_local_fallback_sandbox(agent.sandbox_id):
        return {
            "output": LOCAL_FALLBACK_SANDBOX_ERROR,
            "exit_code": 1,
            "sandbox_id": agent.sandbox_id,
        }

    if AsyncSandbox is None:
        return {
            "output": "E2B SDK not available in this environment.",
            "exit_code": 1,
            "sandbox_id": agent.sandbox_id,
        }

    os.environ["E2B_API_KEY"] = settings.e2b_api_key
    sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
    proc = await sandbox.process.start(body.command, timeout=body.timeout)
    await proc.wait()

    output_parts: list[str] = []
    if proc.stdout:
        output_parts.append(proc.stdout)
    if proc.stderr:
        output_parts.append(proc.stderr)
    output = "\n".join(part for part in output_parts if part).strip()
    return {"output": output, "exit_code": proc.exit_code, "sandbox_id": agent.sandbox_id}

