"""Internal git contract endpoints."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import verify_agent_request
from backend.db.models import Agent
from backend.db.session import get_db
from backend.services.git_service import GitService

router = APIRouter(prefix="/git", tags=["internal-git"])


class CreateBranchRequest(BaseModel):
    agent_id: UUID
    branch_name: str


class CreatePRRequest(BaseModel):
    agent_id: UUID
    title: str
    description: str | None = None


async def _get_actor(db: AsyncSession, agent_id: UUID) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _repo_path() -> str:
    path = Path(settings.code_repo_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _ensure_git_repo(repo_path: str) -> None:
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--is-inside-work-tree"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as exc:
        detail = (exc.output or "").strip()
        message = detail or f"Git repository not initialized at {repo_path}."
        raise HTTPException(status_code=400, detail=message) from exc
    if output != "true":
        raise HTTPException(
            status_code=400,
            detail=f"Git repository not initialized at {repo_path}.",
        )


@router.post("/create-branch")
async def create_branch(
    body: CreateBranchRequest,
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(auth_agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    actor = await _get_actor(db, body.agent_id)
    if actor.role not in {"cto", "engineer"}:
        raise HTTPException(status_code=403, detail="Only cto/engineer can create branches")
    service = GitService(repo_path=_repo_path())
    branch = service.create_branch(actor.role, body.branch_name)
    return {"branch_name": branch}


@router.post("/create-pr")
async def create_pr(
    body: CreatePRRequest,
    auth_agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_id != UUID(auth_agent_id):
        raise HTTPException(status_code=403, detail="agent_id must match authenticated agent")
    actor = await _get_actor(db, body.agent_id)
    if actor.role not in {"cto", "engineer"}:
        raise HTTPException(status_code=403, detail="Only cto/engineer can create PRs")

    # Use current branch as source.
    current_branch = subprocess.check_output(
        ["git", "-C", _repo_path(), "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
    ).strip()
    service = GitService(repo_path=_repo_path())
    result = service.create_pr(actor.role, current_branch, "main")
    return {"pr_url": result.pr_url}


@router.get("/branches")
async def list_branches(
    _auth_agent_id: str = Depends(verify_agent_request),
):
    repo_path = _repo_path()
    _ensure_git_repo(repo_path)
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_path, "branch", "--list"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        message = detail or f"Failed to list branches in repository: {repo_path}"
        raise HTTPException(status_code=400, detail=message) from exc
    branches = [line.replace("*", "").strip() for line in output.splitlines() if line.strip()]
    return {"branches": branches}


@router.get("/diff")
async def view_diff(
    base: str = Query("main"),
    head: str = Query("HEAD"),
    _auth_agent_id: str = Depends(verify_agent_request),
):
    output = subprocess.check_output(
        ["git", "-C", _repo_path(), "diff", f"{base}...{head}"],
        text=True,
    )
    return {"diff": output}

