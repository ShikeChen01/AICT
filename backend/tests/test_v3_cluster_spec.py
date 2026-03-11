"""
Tests for v3 ClusterSpec: YAML parsing, validation, diff, and apply.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.cluster.spec import (
    ClusterSpec,
    ClusterManifest,
    ClusterDiff,
    ClusterDiffItem,
    SandboxSpec,
    BudgetSpec,
    TopologySpec,
    ClusterSpecBody,
    ClusterMetadata,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PROJECT_ID = str(uuid4())
TEMPLATE_ID = str(uuid4())

VALID_YAML = f"""
apiVersion: aict/v1
kind: AgentCluster
metadata:
  name: research-team
  project_id: {PROJECT_ID}
spec:
  replicas: 2
  agent_template: {TEMPLATE_ID}
  model: claude-sonnet-4-6
  display_name_prefix: Research Agent
  sandbox:
    os_image: ubuntu-24.04
    setup_script: "pip install requests"
  budget:
    daily_cost_usd: 5.00
    max_tokens_per_session: 50000
  topology:
    role: worker
  labels:
    team: research
    env: production
"""

MINIMAL_YAML = f"""
apiVersion: aict/v1
kind: AgentCluster
metadata:
  name: minimal
  project_id: {PROJECT_ID}
spec:
  replicas: 1
"""


# ── Parsing tests ─────────────────────────────────────────────────────────────

class TestClusterSpecParsing:

    def test_parse_valid_yaml(self):
        spec, errors = ClusterSpec.from_yaml(VALID_YAML)
        assert errors == []
        assert spec is not None
        assert spec.manifest.cluster_name == "research-team"
        assert spec.manifest.spec.replicas == 2
        assert spec.manifest.spec.model == "claude-sonnet-4-6"

    def test_parse_minimal_yaml(self):
        spec, errors = ClusterSpec.from_yaml(MINIMAL_YAML)
        assert errors == []
        assert spec is not None
        assert spec.manifest.spec.replicas == 1
        # Defaults
        assert spec.manifest.spec.model == "claude-sonnet-4-6"
        assert spec.manifest.spec.sandbox.os_image == "ubuntu-24.04"

    def test_parse_invalid_yaml_syntax(self):
        spec, errors = ClusterSpec.from_yaml("not: valid: yaml: [[[")
        assert spec is None
        assert any("YAML parse error" in e for e in errors)

    def test_parse_missing_required_fields(self):
        spec, errors = ClusterSpec.from_yaml("apiVersion: aict/v1\nkind: AgentCluster\n")
        assert spec is None
        assert len(errors) > 0

    def test_parse_wrong_kind(self):
        yaml_text = f"""
apiVersion: aict/v1
kind: WrongKind
metadata:
  name: test
  project_id: {PROJECT_ID}
spec:
  replicas: 1
"""
        spec, errors = ClusterSpec.from_yaml(yaml_text)
        assert spec is None
        assert any("AgentCluster" in e for e in errors)

    def test_parse_invalid_os_image(self):
        yaml_text = f"""
apiVersion: aict/v1
kind: AgentCluster
metadata:
  name: test
  project_id: {PROJECT_ID}
spec:
  replicas: 1
  sandbox:
    os_image: amiga-os
"""
        spec, errors = ClusterSpec.from_yaml(yaml_text)
        assert spec is None
        assert any("os_image" in e for e in errors)

    def test_parse_invalid_role(self):
        yaml_text = f"""
apiVersion: aict/v1
kind: AgentCluster
metadata:
  name: test
  project_id: {PROJECT_ID}
spec:
  replicas: 1
  topology:
    role: overlord
"""
        spec, errors = ClusterSpec.from_yaml(yaml_text)
        assert spec is None
        assert any("role" in e for e in errors)

    def test_parse_replicas_too_large(self):
        yaml_text = f"""
apiVersion: aict/v1
kind: AgentCluster
metadata:
  name: test
  project_id: {PROJECT_ID}
spec:
  replicas: 999
"""
        spec, errors = ClusterSpec.from_yaml(yaml_text)
        assert spec is None

    def test_roundtrip_yaml(self):
        spec, _ = ClusterSpec.from_yaml(VALID_YAML)
        assert spec is not None
        yaml_out = spec.to_yaml()
        spec2, errors = ClusterSpec.from_yaml(yaml_out)
        assert errors == []
        assert spec2.manifest.cluster_name == spec.manifest.cluster_name
        assert spec2.manifest.spec.replicas == spec.manifest.spec.replicas


# ── Sub-model validation ──────────────────────────────────────────────────────

class TestSubModelValidation:

    def test_sandbox_valid_os_images(self):
        for img in ["ubuntu-22.04", "ubuntu-24.04", "debian-12", "windows-server-2022"]:
            s = SandboxSpec(os_image=img)
            assert s.os_image == img

    def test_budget_all_zeros_no_limit(self):
        b = BudgetSpec()
        assert not b.has_limits

    def test_budget_with_limit(self):
        b = BudgetSpec(daily_cost_usd=5.0)
        assert b.has_limits

    def test_topology_valid_roles(self):
        for role in ["manager", "cto", "engineer", "worker", "researcher", "reviewer"]:
            t = TopologySpec(role=role)
            assert t.role == role

    def test_topology_reports_to_valid_uuid(self):
        uid = str(uuid4())
        t = TopologySpec(reports_to=uid)
        assert t.reports_to == uid

    def test_topology_reports_to_invalid(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TopologySpec(reports_to="not-a-uuid")


# ── Diff tests ────────────────────────────────────────────────────────────────

class TestClusterDiff:

    def test_diff_summary_no_changes(self):
        diff = ClusterDiff(items=[
            ClusterDiffItem("noop", str(uuid4()), "Agent-1", "already converged"),
        ])
        assert not diff.has_changes
        assert "noop" in diff.summary()

    def test_diff_has_changes(self):
        diff = ClusterDiff(items=[
            ClusterDiffItem("create", None, "Agent-1", "new"),
        ])
        assert diff.has_changes

    def test_diff_summary_mixed(self):
        diff = ClusterDiff(items=[
            ClusterDiffItem("create", None, "Agent-1", "new"),
            ClusterDiffItem("delete", str(uuid4()), "Agent-2", "removed"),
            ClusterDiffItem("noop", str(uuid4()), "Agent-3", "ok"),
        ])
        summary = diff.summary()
        assert "create" in summary
        assert "delete" in summary

    @pytest.mark.asyncio
    async def test_compute_diff_all_creates(self):
        """Diff shows all creates when no agents exist."""
        spec, _ = ClusterSpec.from_yaml(MINIMAL_YAML)
        assert spec is not None

        # Mock DB returning no existing agents
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        from uuid import UUID
        diff = await spec.compute_diff(mock_db, UUID(PROJECT_ID))
        assert diff.has_changes
        create_items = [i for i in diff.items if i.action == "create"]
        assert len(create_items) == spec.manifest.spec.replicas

    @pytest.mark.asyncio
    async def test_compute_diff_noop_when_converged(self):
        """Diff shows noop when all agents already match."""
        spec, _ = ClusterSpec.from_yaml(MINIMAL_YAML)

        from backend.db.models import Agent
        from uuid import UUID

        existing_agent = MagicMock(spec=Agent)
        existing_agent.id = uuid4()
        existing_agent.display_name = "minimal-1"
        existing_agent.model = "claude-sonnet-4-6"
        existing_agent.role = "worker"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing_agent]
        mock_db.execute.return_value = mock_result

        diff = await spec.compute_diff(mock_db, UUID(PROJECT_ID))
        noop_items = [i for i in diff.items if i.action == "noop"]
        assert len(noop_items) == 1

    @pytest.mark.asyncio
    async def test_compute_diff_update_on_model_change(self):
        """Diff shows update when model changed."""
        spec, _ = ClusterSpec.from_yaml(MINIMAL_YAML)

        from backend.db.models import Agent
        from uuid import UUID

        existing_agent = MagicMock(spec=Agent)
        existing_agent.id = uuid4()
        existing_agent.display_name = "minimal-1"
        existing_agent.model = "old-model"          # differs from spec's claude-sonnet-4-6
        existing_agent.role = "worker"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing_agent]
        mock_db.execute.return_value = mock_result

        diff = await spec.compute_diff(mock_db, UUID(PROJECT_ID))
        update_items = [i for i in diff.items if i.action == "update"]
        assert len(update_items) == 1
        assert "model" in update_items[0].reason
