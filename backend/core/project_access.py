"""Centralized project access checks.

All API endpoints call `require_project_access()` instead of inlining
the owner_id check. This single function encapsulates the access rule:

  A user may access a repository if:
    (a) the repository has owner_id IS NULL  (legacy compatibility mode), OR
    (b) the user has a row in repository_memberships for that repository.

v3 hardening (code review high #2):
  The legacy NULL owner bypass is now gated behind ALLOW_NULL_OWNER_ACCESS
  env var (default: True for backward compat). Set to "false" or "0" in
  production to enforce strict ownership on all projects.

  This preserves backward compatibility while giving operators a clear
  production knob to eliminate the bypass entirely.
"""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Repository, RepositoryMembership
from backend.db.repositories.membership import MembershipRepository

# Production operators can disable the legacy null-owner bypass.
_ALLOW_NULL_OWNER = os.getenv("ALLOW_NULL_OWNER_ACCESS", "true").lower() not in ("false", "0", "no")


async def require_project_access(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    *,
    owner_only: bool = False,
) -> Repository:
    """Return the Repository if the user has access; raise 404 otherwise.

    Args:
        db: async SQLAlchemy session.
        project_id: target repository UUID.
        user_id: authenticated user UUID.
        owner_only: if True, only 'owner' role grants access (used for
                    destructive operations like delete).
    """
    result = await db.execute(
        select(Repository).where(Repository.id == project_id)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Legacy: unowned repositories accessible to everyone (gated by config)
    if repo.owner_id is None and _ALLOW_NULL_OWNER:
        return repo

    # Strict ownership: must have a membership row
    if repo.owner_id is None and not _ALLOW_NULL_OWNER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    membership_repo = MembershipRepository(db)
    membership = await membership_repo.get(project_id, user_id)

    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if owner_only and membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action",
        )

    return repo


async def add_owner_membership(
    db: AsyncSession,
    repository_id: UUID,
    user_id: UUID,
) -> None:
    """Add an 'owner' membership for the user on the given repository.

    Called immediately after repository creation / import.
    """
    repo = MembershipRepository(db)
    await repo.add(repository_id, user_id, role="owner")
