"""
Git service for agent-safe repository operations.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.core.access_control import (
    enforce_git_merge_permission,
    enforce_git_pr_permission,
    enforce_git_ref_write,
)
from backend.core.exceptions import GitOperationFailed


def _run_git(repo_path: str, *args: str) -> str:
    cmd = ["git", "-C", repo_path, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        reason = stderr or stdout or "unknown git failure"
        raise GitOperationFailed(reason) from exc
    return proc.stdout.strip()


@dataclass(slots=True)
class PROperationResult:
    source_branch: str
    target_branch: str
    pr_url: str


class GitService:
    """Implements guarded git operations for internal agent tooling."""

    def __init__(self, repo_path: str):
        self.repo_path = str(Path(repo_path))

    def create_branch(self, agent_role: str, branch_name: str, base_branch: str = "main") -> str:
        enforce_git_ref_write(agent_role, branch_name)
        _run_git(self.repo_path, "checkout", base_branch)
        _run_git(self.repo_path, "checkout", "-b", branch_name)
        return branch_name

    def commit_all(self, message: str) -> str:
        _run_git(self.repo_path, "add", "-A")
        _run_git(
            self.repo_path,
            "-c",
            "user.name=AICT Bot",
            "-c",
            "user.email=aict-bot@example.com",
            "commit",
            "-m",
            message,
        )
        return _run_git(self.repo_path, "rev-parse", "HEAD")

    def push_branch(self, branch_name: str, remote: str = "origin") -> str:
        _run_git(self.repo_path, "push", "-u", remote, branch_name)
        return branch_name

    def create_pr(
        self,
        agent_role: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> PROperationResult:
        enforce_git_pr_permission(agent_role)
        enforce_git_ref_write(agent_role, source_branch)
        if source_branch == target_branch:
            raise GitOperationFailed("source and target branches must differ")
        pr_url = f"local://pr/{source_branch}-to-{target_branch}"
        return PROperationResult(
            source_branch=source_branch,
            target_branch=target_branch,
            pr_url=pr_url,
        )

    def merge_pr(
        self,
        agent_role: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> str:
        enforce_git_merge_permission(agent_role)
        _run_git(self.repo_path, "checkout", target_branch)
        _run_git(self.repo_path, "merge", "--no-ff", source_branch, "-m", f"Merge {source_branch}")
        return _run_git(self.repo_path, "rev-parse", "HEAD")

