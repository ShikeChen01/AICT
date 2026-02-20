"""
Git tools for LangGraph agents.

All git operations run inside the agent's sandbox container via SandboxService.
"""

import shlex
import uuid

from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.config import settings
from backend.services.git_service import GitService
from backend.services.sandbox_service import SandboxService
from backend.core.exceptions import GitOperationFailed
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

REPO_DIR = "/home/user/project"


async def _run_git_in_sandbox(agent_id: str, command: str) -> str:
    """Run a shell command in the agent's sandbox. Returns combined stdout/stderr or error."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            return "Error: Agent not found."

        svc = SandboxService()
        try:
            shell_result = await svc.execute_command(session, agent, command)
            await session.flush()
            output = f"Command: {command}\nExit Code: {shell_result.exit_code}\n"
            if shell_result.stdout:
                output += f"Stdout:\n{shell_result.stdout}\n"
            return output
        except Exception as exc:
            return f"Sandbox execution failed: {exc}"


@tool
async def create_branch(agent_id: str, branch_name: str) -> str:
    """
    Create a new git branch from main in the agent's sandbox.

    Args:
        agent_id: UUID of the agent (engineer).
        branch_name: The name of the new branch (e.g., 'feat/auth-login').
    """
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
async def create_issue(agent_id: str, title: str, body: str = "", labels: str = "", assignees: str = "") -> str:
    """
    Create a GitHub issue in the project repository.

    Args:
        agent_id: UUID of the agent.
        title: Issue title.
        body: Issue body / description.
        labels: Comma-separated list of label names to apply (optional).
        assignees: Comma-separated list of GitHub usernames to assign (optional).
    """
    label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else None
    assignee_list = [a.strip() for a in assignees.split(",") if a.strip()] if assignees else None
    try:
        git = GitService(settings.code_repo_path)
        result = git.create_issue(title=title, body=body, labels=label_list, assignees=assignee_list)
        return f"Issue created successfully: {result.get('html_url', result)}"
    except GitOperationFailed as exc:
        return f"Issue creation failed: {exc}"


@tool
async def create_github_project(agent_id: str, name: str, body: str = "") -> str:
    """
    Create a GitHub project board in the project repository.

    Args:
        agent_id: UUID of the agent.
        name: Project board name.
        body: Optional description for the project board.
    """
    try:
        git = GitService(settings.code_repo_path)
        result = git.create_github_project(name=name, body=body)
        return f"GitHub project created successfully: {result.get('html_url', result)}"
    except GitOperationFailed as exc:
        return f"GitHub project creation failed: {exc}"


@tool
async def create_pull_request(agent_id: str, source_branch: str) -> str:
    """
    Create a Pull Request from the source branch to main.

    Args:
        agent_id: UUID of the agent (engineer).
        source_branch: The branch containing the changes.
    """
    safe_branch = shlex.quote(source_branch.strip())
    check_cmd = f"cd {REPO_DIR} && git log --oneline -1 {safe_branch}"
    out = await _run_git_in_sandbox(agent_id, check_cmd)
    if "Exit Code: 0" not in out and "fatal:" in out:
        return f"Error: Branch {source_branch} not found in sandbox. Push the branch first.\n{out}"

    try:
        git = GitService(settings.code_repo_path)
        result = git.create_pr("engineer", source_branch)
        return f"PR Created successfully: {result.pr_url}"
    except GitOperationFailed as exc:
        return f"PR creation failed: {exc}"
