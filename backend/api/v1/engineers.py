"""
Engineer graph API: resume interrupted engineer runs.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.auth import verify_token
from backend.services.engineer_graph_service import get_engineer_graph_service

router = APIRouter(prefix="/engineers", tags=["engineers"])


class ResumeBody(BaseModel):
    """Body for resuming an interrupted engineer graph."""

    task_id: str
    message: str


@router.post("/{agent_id}/resume")
async def resume_engineer(
    agent_id: UUID,
    body: ResumeBody,
    _auth: bool = Depends(verify_token),
):
    """
    Resume an interrupted engineer graph with user input.
    Call this when the user has replied to a ticket created by request_human_input.
    """
    try:
        task_uuid = UUID(body.task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id UUID")

    svc = get_engineer_graph_service()
    await svc.resume_engineer(
        agent_id=agent_id,
        task_id=task_uuid,
        user_message=body.message,
    )
    return {"status": "resumed"}
