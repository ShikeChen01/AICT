"""
v3 Cluster Control API — declarative agent cluster management.

Endpoints:
  POST   /clusters/apply          Apply a ClusterSpec manifest (create/update/delete agents)
  POST   /clusters/diff           Preview what apply() would change (dry-run)
  GET    /clusters/{project_id}   Describe live cluster state for a project
  GET    /clusters                List all cluster specs stored for a project
  DELETE /clusters/{project_id}/{cluster_name}  Delete a named cluster

This is the "kubectl apply" equivalent for intelligent agent clusters.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cluster.spec import ClusterSpec, ClusterDiff, ClusterDiffItem
from backend.config import settings
from backend.core.auth import get_current_user, verify_token
from backend.core.project_access import require_project_access
from backend.db.models import Agent, User
from backend.db.session import get_db
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/clusters", tags=["clusters"])


# ── Request / response schemas ────────────────────────────────────────────────


class ApplyRequest(BaseModel):
    """Body for POST /clusters/apply and /clusters/diff."""
    manifest_yaml: str | None = Field(
        default=None,
        description="YAML text of the ClusterSpec manifest",
    )
    manifest: dict | None = Field(
        default=None,
        description="Pre-parsed manifest dict (alternative to manifest_yaml)",
    )


class DiffItemResponse(BaseModel):
    action: str
    agent_id: str | None
    display_name: str
    reason: str


class DiffResponse(BaseModel):
    has_changes: bool
    summary: str
    items: list[DiffItemResponse]


class AgentSummary(BaseModel):
    agent_id: str
    display_name: str
    role: str
    model: str
    status: str
    cluster_name: str | None


class ClusterDescribeResponse(BaseModel):
    project_id: str
    agents: list[AgentSummary]
    cluster_groups: dict[str, list[AgentSummary]]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_manifest(body: ApplyRequest) -> tuple[ClusterSpec | None, list[str]]:
    if body.manifest_yaml:
        return ClusterSpec.from_yaml(body.manifest_yaml)
    if body.manifest:
        return ClusterSpec.from_dict(body.manifest)
    return None, ["Either manifest_yaml or manifest must be provided"]


def _diff_to_response(diff: ClusterDiff) -> DiffResponse:
    return DiffResponse(
        has_changes=diff.has_changes,
        summary=diff.summary(),
        items=[
            DiffItemResponse(
                action=i.action,
                agent_id=i.agent_id,
                display_name=i.display_name,
                reason=i.reason,
            )
            for i in diff.items
        ],
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/diff", response_model=DiffResponse)
async def diff_cluster(
    body: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dry-run: preview what apply() would do without making any changes.

    Equivalent to `kubectl diff -f manifest.yaml`.
    """
    spec, errors = _parse_manifest(body)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"errors": errors})

    await require_project_access(db, spec.project_id, current_user.id)

    diff = await spec.compute_diff(db, spec.project_id)
    return _diff_to_response(diff)


@router.post("/apply", response_model=DiffResponse)
async def apply_cluster(
    body: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply a ClusterSpec manifest — creates, updates, and deletes agents
    to converge the live cluster toward the desired state.

    Equivalent to `kubectl apply -f manifest.yaml`.
    Returns the diff that was applied.
    """
    spec, errors = _parse_manifest(body)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"errors": errors})

    await require_project_access(db, spec.project_id, current_user.id)

    logger.info(
        "Cluster apply: project=%s cluster=%s replicas=%d",
        spec.project_id,
        spec.manifest.cluster_name,
        spec.manifest.spec.replicas,
    )

    diff = await spec.apply(db, spec.project_id)
    return _diff_to_response(diff)


@router.get("/{project_id}", response_model=ClusterDescribeResponse)
async def describe_cluster(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Describe the live cluster state for a project.

    Returns all agents grouped by cluster_name label.
    Equivalent to `kubectl get pods --all-namespaces`.
    """
    await require_project_access(db, project_id, current_user.id)

    result = await db.execute(select(Agent).where(Agent.project_id == project_id))
    agents: list[Agent] = list(result.scalars().all())

    groups: dict[str, list[AgentSummary]] = {}
    summaries: list[AgentSummary] = []

    for agent in agents:
        cluster_name = None
        if agent.memory and isinstance(agent.memory, dict):
            cluster_name = agent.memory.get("cluster_name")

        summary = AgentSummary(
            agent_id=str(agent.id),
            display_name=agent.display_name,
            role=agent.role,
            model=agent.model,
            status=agent.status,
            cluster_name=cluster_name,
        )
        summaries.append(summary)

        group_key = cluster_name or "__ungrouped__"
        groups.setdefault(group_key, []).append(summary)

    return ClusterDescribeResponse(
        project_id=str(project_id),
        agents=summaries,
        cluster_groups=groups,
    )
