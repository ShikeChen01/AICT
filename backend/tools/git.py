"""
Git tools for LangGraph agents.

All git operations run inside the agent's E2B sandbox so that commits
see the same files that write_file/execute_in_sandbox use.
"""

import os
import shlex
import uuid
import logging
from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.config import settings
from backend.services.git_service import GitService
from backend.core.exceptions import GitOperationFailed

logger = logging.getLogger(__name__)

try:
    from e2b import AsyncSandbox
except ImportError:
    AsyncSandbox = None
    logger.warning("E2B SDK not found.")

REPO_DIR = "/home/user/project"


async def _run_git_in_sandbox(agent_id: str, command: str) -> str:
    """Run a shell command in the agent's sandbox. Returns combined stdout/stderr or error message."""
    if AsyncSandbox is None:
        return "Error: E2B SDK not installed."

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            return "Error: Agent not found."

        if not agent.sandbox_id:
            return "Error: Agent has no active sandbox."

        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            sandbox = await AsyncSandbox.connect(
                agent.sandbox_id, timeout=settings.e2b_timeout_seconds
            )
            proc = await sandbox.process.start(command)
            await proc.wait()

            output = f"Command: {command}\nExit Code: {proc.exit_code}\n"
            if proc.stdout:
                output += f"Stdout:\n{proc.stdout}\n"
            if proc.stderr:
                output += f"Stderr:\n{proc.stderr}\n"
            return output

        except Exception as e:
            return f"Sandbox execution failed: {str(e)}"


@tool
async def create_branch(agent_id: str, branch_name: str) -> str:
    """
    Create a new git branch from main in the agent's sandbox.

    Args:
        agent_id: UUID of the agent (engineer).
        branch_name: The name of the new branch (e.g., 'feat/auth-login').
    """
    # Sanitize branch name for shell (no newlines or quotes that could break the command)
    safe_branch = shlex.quote(branch_name.strip())
    command = f"cd {REPO_DIR} && git checkout main && git checkout -b {safe_branch}"
    return await _run_git_in_sandbox(agent_id, command)


@tool
async def commit_changes(agent_id: str, message: str) -> str:
    """
    Commit all current file changes in the agent's sandbox repository.

    Args:
        agent_id: UUID of the agent (engineer).
        message: The commit message.
    """
    safe_message = shlex.quote(message.strip())
    command = (
        f"cd {REPO_DIR} && git add -A && "
        f"git -c user.name='AICT Bot' -c user.email='aict-bot@example.com' commit -m {safe_message}"
    )
    return await _run_git_in_sandbox(agent_id, command)


@tool
async def push_changes(agent_id: str, branch_name: str) -> str:
    """
    Push the specific branch to the remote repository from the agent's sandbox.

    Args:
        agent_id: UUID of the agent (engineer).
        branch_name: The name of the branch to push.
    """
    safe_branch = shlex.quote(branch_name.strip())
    command = f"cd {REPO_DIR} && git push -u origin {safe_branch}"
    return await _run_git_in_sandbox(agent_id, command)


@tool
async def create_pull_request(agent_id: str, source_branch: str) -> str:
    """
    Create a Pull Request from the source branch to main.
    Verifies the branch exists in the sandbox, then uses GitHub API (host) to create the PR.

    Args:
        agent_id: UUID of the agent (engineer).
        source_branch: The branch containing the changes.
    """
    # Verify branch was pushed from sandbox
    safe_branch = shlex.quote(source_branch.strip())
    check_cmd = f"cd {REPO_DIR} && git log --oneline -1 {safe_branch}"
    out = await _run_git_in_sandbox(agent_id, check_cmd)
    if "Exit Code: 0" not in out and "fatal:" in out:
        return f"Error: Branch {source_branch} not found in sandbox. Push the branch first.\n{out}"

    # GitHub API call runs on host (GitService uses host's code_repo_path for remote URL / token)
    try:
        git = GitService(settings.code_repo_path)
        result = git.create_pr("engineer", source_branch)
        return f"PR Created successfully: {result.pr_url}"
    except GitOperationFailed as e:
        return f"PR creation failed: {e}"
