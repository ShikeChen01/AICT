"""
Orchestrator tests — updated for v3.

The legacy Ticket model was removed in v2 (Agent 1). This file was previously
skipped entirely because it tried to import the removed model. Tests have been
rewritten to cover the current OrchestratorService API.

v3 note: sandbox persistence policy is enforced by role; managers and CTOs
get persistent sandboxes, engineers and workers do not.
"""

from __future__ import annotations

import pytest


# ── Sandbox policy tests (no DB needed) ──────────────────────────────────────

class TestSandboxPolicy:

    def test_manager_gets_persistent_sandbox(self):
        from backend.services.orchestrator import sandbox_should_persist
        assert sandbox_should_persist("manager") is True

    def test_cto_gets_persistent_sandbox(self):
        from backend.services.orchestrator import sandbox_should_persist
        assert sandbox_should_persist("cto") is True

    def test_engineer_gets_ephemeral_sandbox(self):
        from backend.services.orchestrator import sandbox_should_persist
        assert sandbox_should_persist("engineer") is False

    def test_worker_gets_ephemeral_sandbox(self):
        from backend.services.orchestrator import sandbox_should_persist
        assert sandbox_should_persist("worker") is False

    def test_invalid_role_raises(self):
        from backend.services.orchestrator import sandbox_should_persist
        from backend.core.exceptions import InvalidAgentRole
        with pytest.raises(InvalidAgentRole):
            sandbox_should_persist("overlord")
