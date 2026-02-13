"""
Git tools for LangGraph agents.
"""

from langchain_core.tools import tool
from backend.services.git_service import GitService
from backend.config import settings

@tool
def create_branch(branch_name: str, agent_role: str = "engineer") -> str:
    """
    Create a new git branch from main.
    
    Args:
        branch_name: The name of the new branch (e.g., 'feat/auth-login').
        agent_role: The role of the agent creating the branch (default: 'engineer').
    """
    git = GitService(settings.code_repo_path)
    return git.create_branch(agent_role, branch_name)

@tool
def commit_changes(message: str) -> str:
    """
    Commit all current file changes in the repository.
    
    Args:
        message: The commit message.
    """
    git = GitService(settings.code_repo_path)
    return git.commit_all(message)

@tool
def push_changes(branch_name: str) -> str:
    """
    Push the specific branch to the remote repository.
    
    Args:
        branch_name: The name of the branch to push.
    """
    git = GitService(settings.code_repo_path)
    return git.push_branch(branch_name)

@tool
def create_pull_request(source_branch: str, agent_role: str = "engineer") -> str:
    """
    Create a Pull Request from the source branch to main.
    
    Args:
        source_branch: The branch containing the changes.
        agent_role: The role of the agent creating the PR.
    """
    git = GitService(settings.code_repo_path)
    result = git.create_pr(agent_role, source_branch)
    return f"PR Created successfully: {result.pr_url}"
