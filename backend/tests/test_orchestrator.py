"""
Orchestrator tests — updated for v3.1.

v3.1: sandbox persistence is no longer role-based. The sandbox_should_persist()
function has been removed. Sandboxes are user-owned resources with explicit
lifecycle management.

These tests now cover the OrchestratorService's simplified API.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOrchestratorServiceSimplified:
    """Verify the simplified OrchestratorService behaves correctly."""

    def test_shutdown_graph_runtime_is_noop(self):
        from backend.services.orchestrator import shutdown_graph_runtime
        # Should not raise — it's a no-op after graph removal
        shutdown_graph_runtime()

    @pytest.mark.asyncio
    async def test_orchestrator_service_instantiates(self):
        from backend.services.orchestrator import OrchestratorService
        svc = OrchestratorService()
        assert svc is not None

    @pytest.mark.asyncio
    async def test_close_if_ephemeral_is_noop(self):
        """close_if_ephemeral was kept for backward compat but does nothing."""
        from backend.services.orchestrator import OrchestratorService

        svc = OrchestratorService()
        agent = MagicMock()
        agent.id = "test-agent-id"
        session = MagicMock()

        # Should not raise
        await svc.close_if_ephemeral(session, agent)
