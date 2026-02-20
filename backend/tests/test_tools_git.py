"""
Unit tests for git tools (sandbox-based).

Tests _run_git_in_sandbox behavior and tool error paths without a real sandbox VM.
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.tools.git import (
    _run_git_in_sandbox,
    create_branch,
    commit_changes,
    push_changes,
    REPO_DIR,
)
from backend.services.sandbox_client import ShellResult


class _SessionContext:
    """Async context manager that yields the test session."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def agent_with_sandbox(sample_engineer):
    """Engineer with sandbox_id set."""
    sample_engineer.sandbox_id = "sandbox-abc123"
    return sample_engineer


@pytest.fixture
def agent_no_sandbox(sample_engineer):
    """Engineer with no sandbox."""
    sample_engineer.sandbox_id = None
    return sample_engineer


class TestRunGitInSandbox:
    """Tests for _run_git_in_sandbox."""

    @pytest.mark.asyncio
    async def test_agent_not_found(self, session):
        """Unknown agent_id returns error message."""
        await session.commit()
        bad_id = str(uuid.uuid4())
        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            result = await _run_git_in_sandbox(bad_id, "git status")
        assert "Agent not found" in result or "Error" in result

    @pytest.mark.asyncio
    async def test_agent_no_sandbox_returns_offline_result(self, session, agent_no_sandbox):
        """Agent without sandbox_id gets an offline sandbox (no VM configured in test env)."""
        await session.commit()
        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            result = await _run_git_in_sandbox(str(agent_no_sandbox.id), "git status")
        # offline guard fires when sandbox_vm_host is not set
        assert "offline" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_sandbox_connect_and_run(self, session, agent_with_sandbox):
        """With mocked SandboxService, command runs and returns stdout."""
        await session.commit()
        shell_result = ShellResult(stdout="On branch main\n", exit_code=0)

        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            with patch("backend.tools.git.SandboxService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.execute_command = AsyncMock(return_value=shell_result)
                MockSvc.return_value = mock_svc
                result = await _run_git_in_sandbox(
                    str(agent_with_sandbox.id), f"cd {REPO_DIR} && git status"
                )
        assert "Exit Code: 0" in result
        assert "On branch main" in result


class TestCreateBranch:
    """Tests for create_branch tool."""

    @pytest.mark.asyncio
    async def test_create_branch_invokes_sandbox(self, session, agent_with_sandbox):
        """create_branch builds correct command and runs in sandbox."""
        await session.commit()
        shell_result = ShellResult(stdout="Switched to a new branch 'feat/test'\n", exit_code=0)

        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            with patch("backend.tools.git.SandboxService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.execute_command = AsyncMock(return_value=shell_result)
                MockSvc.return_value = mock_svc
                result = await create_branch.ainvoke(
                    {"agent_id": str(agent_with_sandbox.id), "branch_name": "feat/test"}
                )
        assert "feat/test" in result or "Exit Code" in result
        call_args = mock_svc.execute_command.call_args[0][2]  # command is 3rd positional arg
        assert "checkout -b" in call_args
        assert "feat/test" in call_args


class TestCommitChanges:
    """Tests for commit_changes tool."""

    @pytest.mark.asyncio
    async def test_commit_changes_invokes_sandbox(self, session, agent_with_sandbox):
        """commit_changes runs git add and commit in sandbox."""
        await session.commit()
        shell_result = ShellResult(stdout="[main abc1234] Add feature\n", exit_code=0)

        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            with patch("backend.tools.git.SandboxService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.execute_command = AsyncMock(return_value=shell_result)
                MockSvc.return_value = mock_svc
                await commit_changes.ainvoke(
                    {"agent_id": str(agent_with_sandbox.id), "message": "Add feature"}
                )
        call_args = mock_svc.execute_command.call_args[0][2]
        assert "add -A" in call_args or "commit" in call_args


class TestPushChanges:
    """Tests for push_changes tool."""

    @pytest.mark.asyncio
    async def test_push_invokes_sandbox(self, session, agent_with_sandbox):
        """push_changes runs git push in sandbox."""
        await session.commit()
        shell_result = ShellResult(stdout="Branch 'feat/test' set up to track...\n", exit_code=0)

        with patch(
            "backend.tools.git.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            with patch("backend.tools.git.SandboxService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.execute_command = AsyncMock(return_value=shell_result)
                MockSvc.return_value = mock_svc
                await push_changes.ainvoke(
                    {"agent_id": str(agent_with_sandbox.id), "branch_name": "feat/test"}
                )
        call_args = mock_svc.execute_command.call_args[0][2]
        assert "push" in call_args
        assert "feat/test" in call_args
