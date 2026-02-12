"""
Internal file tool endpoints with role-based access control.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.access_control import enforce_file_read, enforce_file_write
from backend.core.auth import verify_agent_request
from backend.core.exceptions import AgentNotFoundError, ScopeViolationError
from backend.db.models import Agent
from backend.db.session import get_db

router = APIRouter(prefix="/files", tags=["internal-files"])


class ReadFileRequest(BaseModel):
    path: str
    module_path: str | None = None


class WriteFileRequest(BaseModel):
    path: str
    content: str
    module_path: str | None = None


class ListDirRequest(BaseModel):
    path: str
    module_path: str | None = None


def _resolve_path(root: str, requested_path: str) -> Path:
    root_path = Path(root).resolve()
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve()
    if root_path != resolved and root_path not in resolved.parents:
        raise ScopeViolationError(f"Path '{requested_path}' escapes repository root '{root}'")
    return resolved


async def _load_actor_agent(session: AsyncSession, actor_agent_id: str) -> Agent:
    try:
        agent_uuid = uuid.UUID(actor_agent_id)
    except ValueError as exc:
        raise AgentNotFoundError(actor_agent_id) from exc
    result = await session.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFoundError(actor_agent_id)
    return agent


def _roots() -> tuple[str, str]:
    return settings.spec_repo_path, settings.code_repo_path


def _pick_target_path(requested: str, spec_root: str, code_root: str) -> Path:
    spec_path = _resolve_path(spec_root, requested)
    code_path = _resolve_path(code_root, requested)
    if spec_path.exists() and not code_path.exists():
        return spec_path
    if code_path.exists() and not spec_path.exists():
        return code_path
    # Default for new files: .tex goes to specs, everything else to code.
    if Path(requested).suffix.lower() == ".tex":
        return spec_path
    return code_path


@router.post("/read")
async def read_file(
    req: ReadFileRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    actor = await _load_actor_agent(session, actor_agent_id)
    spec_root, code_root = _roots()
    chosen = _pick_target_path(req.path, spec_root, code_root)
    enforce_file_read(
        agent_role=actor.role,
        absolute_file_path=str(chosen),
        spec_repo_root=spec_root,
        code_repo_root=code_root,
        module_path=req.module_path,
    )
    if not chosen.exists():
        raise ScopeViolationError(f"Path '{req.path}' does not exist")
    content = chosen.read_text(encoding="utf-8")
    return {"actor_agent_id": actor_agent_id, "path": str(chosen), "content": content}


@router.post("/write")
async def write_file(
    req: WriteFileRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    actor = await _load_actor_agent(session, actor_agent_id)
    spec_root, code_root = _roots()
    chosen = _pick_target_path(req.path, spec_root, code_root)

    enforce_file_write(
        agent_role=actor.role,
        absolute_file_path=str(chosen),
        spec_repo_root=spec_root,
        code_repo_root=code_root,
        module_path=req.module_path,
    )
    chosen.parent.mkdir(parents=True, exist_ok=True)
    chosen.write_text(req.content, encoding="utf-8")
    return {"actor_agent_id": actor_agent_id, "path": str(chosen), "bytes_written": len(req.content)}


@router.post("/list")
async def list_dir(
    req: ListDirRequest,
    actor_agent_id: str = Depends(verify_agent_request),
    session: AsyncSession = Depends(get_db),
):
    actor = await _load_actor_agent(session, actor_agent_id)
    spec_root, code_root = _roots()
    base_path = _pick_target_path(req.path, spec_root, code_root)
    if not base_path.exists():
        raise ScopeViolationError(f"Path '{req.path}' does not exist")

    enforce_file_read(
        agent_role=actor.role,
        absolute_file_path=str(base_path),
        spec_repo_root=spec_root,
        code_repo_root=code_root,
        module_path=req.module_path,
    )
    if not base_path.is_dir():
        raise ScopeViolationError(f"Path '{req.path}' is not a directory")
    entries = [p.name for p in sorted(base_path.iterdir(), key=lambda p: p.name.lower())]
    return {"actor_agent_id": actor_agent_id, "path": str(base_path), "entries": entries}

