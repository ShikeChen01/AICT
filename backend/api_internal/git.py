"""
Internal git tool endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.auth import verify_agent_request
from backend.services.git_service import GitService

router = APIRouter(prefix="/git", tags=["internal-git"])


class BranchRequest(BaseModel):
    agent_role: str
    branch_name: str
    base_branch: str = "main"
    repo_path: str | None = None


class CommitRequest(BaseModel):
    message: str = Field(min_length=1)
    repo_path: str | None = None


class PushRequest(BaseModel):
    branch_name: str
    remote: str = "origin"
    repo_path: str | None = None


class PRRequest(BaseModel):
    agent_role: str
    source_branch: str
    target_branch: str = "main"
    repo_path: str | None = None


class MergeRequest(BaseModel):
    agent_role: str
    source_branch: str
    target_branch: str = "main"
    repo_path: str | None = None


def _service_for(repo_path: str | None) -> GitService:
    return GitService(repo_path=repo_path or settings.code_repo_path)


@router.post("/branch")
async def create_branch(req: BranchRequest, actor_agent_id: str = Depends(verify_agent_request)):
    service = _service_for(req.repo_path)
    branch = service.create_branch(
        agent_role=req.agent_role,
        branch_name=req.branch_name,
        base_branch=req.base_branch,
    )
    return {"actor_agent_id": actor_agent_id, "branch_name": branch}


@router.post("/commit")
async def commit(req: CommitRequest, actor_agent_id: str = Depends(verify_agent_request)):
    service = _service_for(req.repo_path)
    commit_sha = service.commit_all(req.message)
    return {"actor_agent_id": actor_agent_id, "commit_sha": commit_sha}


@router.post("/push")
async def push(req: PushRequest, actor_agent_id: str = Depends(verify_agent_request)):
    service = _service_for(req.repo_path)
    branch = service.push_branch(req.branch_name, req.remote)
    return {"actor_agent_id": actor_agent_id, "branch_name": branch}


@router.post("/pr")
async def create_pr(req: PRRequest, actor_agent_id: str = Depends(verify_agent_request)):
    service = _service_for(req.repo_path)
    result = service.create_pr(
        agent_role=req.agent_role,
        source_branch=req.source_branch,
        target_branch=req.target_branch,
    )
    return {
        "actor_agent_id": actor_agent_id,
        "source_branch": result.source_branch,
        "target_branch": result.target_branch,
        "pr_url": result.pr_url,
    }


@router.post("/merge")
async def merge(req: MergeRequest, actor_agent_id: str = Depends(verify_agent_request)):
    service = _service_for(req.repo_path)
    merge_sha = service.merge_pr(
        agent_role=req.agent_role,
        source_branch=req.source_branch,
        target_branch=req.target_branch,
    )
    return {"actor_agent_id": actor_agent_id, "merge_sha": merge_sha}

