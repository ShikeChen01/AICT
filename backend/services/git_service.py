"""
Git service for agent-safe repository operations.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.config import settings
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
        self.github_token = settings.github_token
        self.github_api_base_url = settings.github_api_base_url.rstrip("/")

    def _origin_remote_url(self) -> str | None:
        try:
            remote_url = _run_git(self.repo_path, "remote", "get-url", "origin")
            return remote_url.strip() or None
        except GitOperationFailed:
            return None

    @staticmethod
    def _github_repo_slug(remote_url: str | None) -> str | None:
        if not remote_url:
            return None

        cleaned = remote_url.strip()
        slug = ""
        if cleaned.startswith("git@github.com:"):
            slug = cleaned.split("git@github.com:", 1)[1]
        elif "github.com/" in cleaned:
            slug = cleaned.split("github.com/", 1)[1]
        else:
            return None

        if slug.endswith(".git"):
            slug = slug[:-4]
        slug = slug.strip("/")
        if slug.count("/") != 1:
            return None
        return slug

    def _github_ready(self) -> tuple[bool, str | None]:
        remote_url = self._origin_remote_url()
        slug = self._github_repo_slug(remote_url)
        return bool(self.github_token and slug), slug

    def _github_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _find_open_pr_number(
        self,
        repo_slug: str,
        source_branch: str,
        target_branch: str,
    ) -> int | None:
        owner = repo_slug.split("/", 1)[0]
        params = {
            "state": "open",
            "head": f"{owner}:{source_branch}",
            "base": target_branch,
            "per_page": 1,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.github_api_base_url}/repos/{repo_slug}/pulls",
                headers=self._github_headers(),
                params=params,
            )
            resp.raise_for_status()
            pulls = resp.json()
        if not pulls:
            return None
        return int(pulls[0]["number"])

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

        github_ready, repo_slug = self._github_ready()
        if github_ready and repo_slug:
            payload = {
                "title": f"{source_branch} -> {target_branch}",
                "head": source_branch,
                "base": target_branch,
                "body": "Automated PR created by AICT.",
                "maintainer_can_modify": True,
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.github_api_base_url}/repos/{repo_slug}/pulls",
                    headers=self._github_headers(),
                    json=payload,
                )

                if resp.status_code == 201:
                    pr_url = resp.json().get("html_url", "")
                elif resp.status_code == 422:
                    pr_number = self._find_open_pr_number(
                        repo_slug=repo_slug,
                        source_branch=source_branch,
                        target_branch=target_branch,
                    )
                    if not pr_number:
                        raise GitOperationFailed(
                            f"GitHub rejected PR creation: {resp.text}"
                        )
                    details_resp = client.get(
                        f"{self.github_api_base_url}/repos/{repo_slug}/pulls/{pr_number}",
                        headers=self._github_headers(),
                    )
                    details_resp.raise_for_status()
                    pr_url = details_resp.json().get("html_url", "")
                else:
                    raise GitOperationFailed(
                        f"GitHub PR creation failed: {resp.status_code} {resp.text}"
                    )

            if not pr_url:
                raise GitOperationFailed("GitHub PR creation succeeded without URL")
        else:
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

        github_ready, repo_slug = self._github_ready()
        if github_ready and repo_slug:
            pr_number = self._find_open_pr_number(
                repo_slug=repo_slug,
                source_branch=source_branch,
                target_branch=target_branch,
            )
            if not pr_number:
                raise GitOperationFailed(
                    f"No open PR found for {source_branch} -> {target_branch}"
                )

            payload = {
                "commit_title": f"Merge {source_branch}",
                "merge_method": "squash",
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.put(
                    f"{self.github_api_base_url}/repos/{repo_slug}/pulls/{pr_number}/merge",
                    headers=self._github_headers(),
                    json=payload,
                )
                if resp.status_code not in (200, 201):
                    raise GitOperationFailed(
                        f"GitHub merge failed: {resp.status_code} {resp.text}"
                    )
                data = resp.json()
            merge_sha = data.get("sha", "")
            if not merge_sha:
                raise GitOperationFailed("GitHub merge succeeded without SHA")
            return merge_sha

        _run_git(self.repo_path, "checkout", target_branch)
        _run_git(self.repo_path, "merge", "--no-ff", source_branch, "-m", f"Merge {source_branch}")
        return _run_git(self.repo_path, "rev-parse", "HEAD")

