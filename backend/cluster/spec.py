"""
ClusterSpec: declarative YAML schema for agent cluster definitions (v3).

Follows Kubernetes-style resource manifests:

    apiVersion: aict/v1
    kind: AgentCluster
    metadata:
      name: research-team
      project_id: <uuid>
    spec:
      replicas: 2
      agent_template: <template-uuid>
      model: claude-sonnet-4-6
      sandbox:
        os_image: ubuntu-24.04
        setup_script: |
          pip install requests
      budget:
        daily_cost_usd: 5.00
        max_tokens_per_session: 50000
      topology:
        role: worker
        reports_to: <agent-uuid>   # optional manager agent
      labels:
        team: research
        env: production

Usage:
    spec = ClusterSpec.from_yaml(yaml_text)
    errors = spec.validate()
    if not errors:
        diff = await spec.diff(db, project_id)
        await spec.apply(db, project_id)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError


# ── Sub-models ────────────────────────────────────────────────────────────────


class SandboxSpec(BaseModel):
    os_image: str = "ubuntu-24.04"
    setup_script: str = ""

    @field_validator("os_image")
    @classmethod
    def validate_os_image(cls, v: str) -> str:
        allowed = {"ubuntu-22.04", "ubuntu-24.04", "debian-12", "windows-server-2022"}
        if v not in allowed:
            raise ValueError(f"os_image must be one of {sorted(allowed)}, got '{v}'")
        return v


class BudgetSpec(BaseModel):
    daily_cost_usd: float = Field(default=0.0, ge=0)
    max_tokens_per_session: int = Field(default=0, ge=0)
    max_pod_seconds_per_day: int = Field(default=0, ge=0)

    @property
    def has_limits(self) -> bool:
        return self.daily_cost_usd > 0 or self.max_tokens_per_session > 0 or self.max_pod_seconds_per_day > 0


class TopologySpec(BaseModel):
    role: str = "worker"
    reports_to: str | None = None   # agent UUID as string

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"manager", "cto", "engineer", "worker", "researcher", "reviewer"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}, got '{v}'")
        return v

    @field_validator("reports_to")
    @classmethod
    def validate_reports_to(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"reports_to must be a valid UUID, got '{v}'") from exc
        return v


class ClusterSpecBody(BaseModel):
    """The 'spec:' block of the manifest."""
    replicas: int = Field(default=1, ge=1, le=20)
    agent_template: str | None = None   # AgentTemplate UUID
    model: str = "claude-sonnet-4-6"
    display_name_prefix: str = ""       # e.g. "Research Agent" -> "Research Agent-1", "Research Agent-2"
    sandbox: SandboxSpec = Field(default_factory=SandboxSpec)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    topology: TopologySpec = Field(default_factory=TopologySpec)
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("agent_template")
    @classmethod
    def validate_agent_template(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"agent_template must be a valid UUID, got '{v}'") from exc
        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: dict) -> dict:
        for k, val in v.items():
            if not re.match(r"^[a-zA-Z0-9_\-./]{1,63}$", k):
                raise ValueError(f"Invalid label key '{k}'")
            if not isinstance(val, str):
                raise ValueError(f"Label value for '{k}' must be a string")
        return v


class ClusterMetadata(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    project_id: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,98}[a-zA-Z0-9]?$", v):
            raise ValueError(
                f"name must be 1-100 chars, start/end with alphanumeric, "
                f"allow hyphens/underscores in between. Got '{v}'"
            )
        return v

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"project_id must be a valid UUID, got '{v}'") from exc
        return v


# ── Top-level manifest ────────────────────────────────────────────────────────


class ClusterManifest(BaseModel):
    """Full cluster manifest — matches the Kubernetes-style YAML structure."""
    api_version: str = Field(alias="apiVersion", default="aict/v1")
    kind: str = "AgentCluster"
    metadata: ClusterMetadata
    spec: ClusterSpecBody

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_kind(self) -> "ClusterManifest":
        if self.kind != "AgentCluster":
            raise ValueError(f"kind must be 'AgentCluster', got '{self.kind}'")
        if self.api_version not in {"aict/v1", "aict/v1alpha1"}:
            raise ValueError(f"apiVersion must be 'aict/v1', got '{self.api_version}'")
        return self

    @property
    def project_id(self) -> UUID:
        return UUID(self.metadata.project_id)

    @property
    def cluster_name(self) -> str:
        return self.metadata.name


# ── Public API ────────────────────────────────────────────────────────────────


@dataclass
class ClusterDiffItem:
    """One item in a spec diff."""
    action: str          # "create" | "update" | "delete" | "noop"
    agent_id: str | None
    display_name: str
    reason: str


@dataclass
class ClusterDiff:
    items: list[ClusterDiffItem] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(i.action != "noop" for i in self.items)

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.action] = counts.get(item.action, 0) + 1
        parts = [f"{v} {k}" for k, v in counts.items()]
        return ", ".join(parts) if parts else "no changes"


class ClusterSpec:
    """
    Parsed and validated cluster spec.

    Usage:
        spec, errors = ClusterSpec.from_yaml(yaml_text)
        if errors:
            raise ValueError(errors)
        diff = await spec.compute_diff(db, project_id)
        await spec.apply(db, project_id)
    """

    def __init__(self, manifest: ClusterManifest) -> None:
        self.manifest = manifest

    @classmethod
    def from_yaml(cls, yaml_text: str) -> tuple["ClusterSpec | None", list[str]]:
        """
        Parse and validate a YAML cluster manifest.

        Returns (ClusterSpec, []) on success, (None, [error_strings]) on failure.
        """
        try:
            raw: Any = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            return None, [f"YAML parse error: {exc}"]

        if not isinstance(raw, dict):
            return None, ["manifest must be a YAML mapping"]

        try:
            manifest = ClusterManifest.model_validate(raw)
        except PydanticValidationError as exc:
            errors = []
            for e in exc.errors():
                loc = " -> ".join(str(p) for p in e["loc"])
                errors.append(f"{loc}: {e['msg']}")
            return None, errors

        return cls(manifest), []

    @classmethod
    def from_dict(cls, data: dict) -> tuple["ClusterSpec | None", list[str]]:
        """Parse from an already-decoded dict."""
        try:
            manifest = ClusterManifest.model_validate(data)
        except PydanticValidationError as exc:
            errors = []
            for e in exc.errors():
                loc = " -> ".join(str(p) for p in e["loc"])
                errors.append(f"{loc}: {e['msg']}")
            return None, errors
        return cls(manifest), []

    def to_dict(self) -> dict:
        return self.manifest.model_dump(mode="json", by_alias=True)

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    async def compute_diff(self, db, project_id: UUID) -> ClusterDiff:
        """
        Compute the diff between this spec and the live cluster state.

        Returns a ClusterDiff describing what would change on apply().
        """
        from sqlalchemy import select
        from backend.db.models import Agent

        s = self.manifest.spec
        desired_role = s.topology.role
        desired_replicas = s.replicas
        prefix = s.display_name_prefix or self.manifest.cluster_name

        # Find existing agents for this cluster (identified by label cluster_name)
        result = await db.execute(
            select(Agent).where(
                Agent.project_id == project_id,
                Agent.role == desired_role,
            )
        )
        existing: list[Agent] = list(result.scalars().all())

        # Match by display_name prefix convention
        cluster_agents = [
            a for a in existing
            if a.display_name.startswith(prefix)
        ]

        diff = ClusterDiff()
        desired_names = [f"{prefix}-{i+1}" for i in range(desired_replicas)]

        existing_names = {a.display_name: a for a in cluster_agents}

        for name in desired_names:
            if name not in existing_names:
                diff.items.append(ClusterDiffItem(
                    action="create",
                    agent_id=None,
                    display_name=name,
                    reason="desired replica not in live cluster",
                ))
            else:
                agent = existing_names[name]
                changes = _detect_agent_changes(agent, s)
                if changes:
                    diff.items.append(ClusterDiffItem(
                        action="update",
                        agent_id=str(agent.id),
                        display_name=name,
                        reason="; ".join(changes),
                    ))
                else:
                    diff.items.append(ClusterDiffItem(
                        action="noop",
                        agent_id=str(agent.id),
                        display_name=name,
                        reason="already converged",
                    ))

        # Agents that exist but are no longer desired
        for name, agent in existing_names.items():
            if name not in desired_names:
                diff.items.append(ClusterDiffItem(
                    action="delete",
                    agent_id=str(agent.id),
                    display_name=name,
                    reason="replica count reduced",
                ))

        return diff

    async def apply(self, db, project_id: UUID) -> ClusterDiff:
        """
        Apply this spec to the live cluster.

        Creates, updates, or deletes agents to match the desired state.
        Returns the diff that was applied.
        """
        from sqlalchemy import select
        from backend.db.models import Agent
        from backend.config import settings as _settings
        from backend.workers.worker_manager import get_worker_manager

        diff = await self.compute_diff(db, project_id)
        s = self.manifest.spec
        prefix = s.display_name_prefix or self.manifest.cluster_name
        wm = get_worker_manager()

        for item in diff.items:
            if item.action == "create":
                agent = Agent(
                    project_id=project_id,
                    role=s.topology.role,
                    display_name=item.display_name,
                    model=s.model,
                    status="sleeping",
                    sandbox_persist=False,
                    template_id=uuid.UUID(s.agent_template) if s.agent_template else None,
                )
                # Store cluster labels in agent memory for tracking
                agent.memory = {
                    "cluster_name": self.manifest.cluster_name,
                    "cluster_labels": s.labels,
                    **(agent.memory or {}),
                }
                db.add(agent)
                await db.flush()  # get the ID
                await wm.spawn_worker(agent.id, project_id)

            elif item.action == "update" and item.agent_id:
                result = await db.execute(
                    select(Agent).where(Agent.id == uuid.UUID(item.agent_id))
                )
                agent = result.scalar_one_or_none()
                if agent:
                    agent.model = s.model
                    if agent.memory is None:
                        agent.memory = {}
                    agent.memory = {
                        **agent.memory,
                        "cluster_name": self.manifest.cluster_name,
                        "cluster_labels": s.labels,
                    }

            elif item.action == "delete" and item.agent_id:
                agent_id = uuid.UUID(item.agent_id)
                await wm.remove_worker(agent_id)
                result = await db.execute(
                    select(Agent).where(Agent.id == agent_id)
                )
                agent = result.scalar_one_or_none()
                if agent:
                    await db.delete(agent)

        await db.commit()
        return diff


def _detect_agent_changes(agent, spec: ClusterSpecBody) -> list[str]:
    """Return a list of human-readable change reasons between live agent and desired spec."""
    changes = []
    if agent.model != spec.model:
        changes.append(f"model: {agent.model} -> {spec.model}")
    if agent.role != spec.topology.role:
        changes.append(f"role: {agent.role} -> {spec.topology.role}")
    return changes
