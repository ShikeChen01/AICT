"""
Tests for custom exceptions and error handler mapping.
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.exceptions import (
    AgentNotFoundError,
    GitOperationBlocked,
    GitOperationFailed,
    InvalidAgentRole,
    InvalidTaskStatus,
    MaxEngineersReached,
    ProjectNotFoundError,
    SandboxNotFoundError,
    ScopeViolationError,
    TaskNotFoundError,
    TicketCloseNotAllowed,
    TicketNotFoundError,
)


# ── Exception message tests ─────────────────────────────────────────


class TestExceptionMessages:
    def test_task_not_found(self):
        exc = TaskNotFoundError("abc-123")
        assert "abc-123" in str(exc)
        assert exc.task_id == "abc-123"

    def test_agent_not_found(self):
        exc = AgentNotFoundError("agent-456")
        assert "agent-456" in str(exc)
        assert exc.agent_id == "agent-456"

    def test_ticket_not_found(self):
        exc = TicketNotFoundError("ticket-789")
        assert "ticket-789" in str(exc)

    def test_project_not_found(self):
        exc = ProjectNotFoundError("proj-000")
        assert "proj-000" in str(exc)

    def test_git_operation_blocked(self):
        exc = GitOperationBlocked("rebase is not allowed")
        assert "rebase" in str(exc)

    def test_git_operation_failed(self):
        exc = GitOperationFailed("merge conflict")
        assert "merge conflict" in str(exc)

    def test_sandbox_not_found(self):
        exc = SandboxNotFoundError("sandbox-id")
        assert "sandbox-id" in str(exc)

    def test_scope_violation(self):
        exc = ScopeViolationError("cannot access /secret")
        assert "/secret" in str(exc)

    def test_max_engineers_default(self):
        exc = MaxEngineersReached()
        assert "5" in str(exc)
        assert exc.limit == 5

    def test_max_engineers_custom(self):
        exc = MaxEngineersReached(limit=3)
        assert "3" in str(exc)
        assert exc.limit == 3

    def test_ticket_close_not_allowed(self):
        exc = TicketCloseNotAllowed("lower priority cannot close")
        assert "lower priority" in str(exc)

    def test_invalid_agent_role(self):
        exc = InvalidAgentRole("hacker")
        assert "hacker" in str(exc)
        assert exc.role == "hacker"

    def test_invalid_task_status(self):
        exc = InvalidTaskStatus("flying")
        assert "flying" in str(exc)
        assert exc.status == "flying"


# ── Error handler integration test ──────────────────────────────────


class TestErrorHandler:
    """Test that the FastAPI error handler returns correct status codes."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI

        from backend.core.error_handlers import aict_exception_handler
        from backend.core.exceptions import AICTException

        app = FastAPI()
        app.add_exception_handler(AICTException, aict_exception_handler)

        @app.get("/task-not-found")
        async def raise_task_not_found():
            raise TaskNotFoundError("t-1")

        @app.get("/git-blocked")
        async def raise_git_blocked():
            raise GitOperationBlocked("rebase blocked")

        @app.get("/scope-violation")
        async def raise_scope_violation():
            raise ScopeViolationError("out of scope")

        @app.get("/max-engineers")
        async def raise_max_engineers():
            raise MaxEngineersReached()

        @app.get("/git-failed")
        async def raise_git_failed():
            raise GitOperationFailed("merge conflict")

        @app.get("/invalid-role")
        async def raise_invalid_role():
            raise InvalidAgentRole("ghost")

        return TestClient(app)

    def test_404_for_task_not_found(self, client):
        resp = client.get("/task-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["type"] == "TaskNotFoundError"

    def test_403_for_git_blocked(self, client):
        resp = client.get("/git-blocked")
        assert resp.status_code == 403
        assert resp.json()["type"] == "GitOperationBlocked"

    def test_403_for_scope_violation(self, client):
        resp = client.get("/scope-violation")
        assert resp.status_code == 403
        assert resp.json()["type"] == "ScopeViolationError"

    def test_400_for_max_engineers(self, client):
        resp = client.get("/max-engineers")
        assert resp.status_code == 400
        assert resp.json()["type"] == "MaxEngineersReached"

    def test_500_for_git_failed(self, client):
        resp = client.get("/git-failed")
        assert resp.status_code == 500
        assert resp.json()["type"] == "GitOperationFailed"

    def test_400_for_invalid_role(self, client):
        resp = client.get("/invalid-role")
        assert resp.status_code == 400
        assert resp.json()["type"] == "InvalidAgentRole"
