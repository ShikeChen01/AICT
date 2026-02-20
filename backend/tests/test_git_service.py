import subprocess
from pathlib import Path

import pytest

from backend.core.exceptions import GitOperationBlocked, GitOperationFailed
from backend.services.git_service import GitService


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    remote.mkdir()
    work.mkdir()
    _run(["git", "init", "--bare"], remote)
    _run(["git", "init", "-b", "main"], work)
    _run(["git", "remote", "add", "origin", str(remote)], work)
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "README.md"], work)
    _run(
        [
            "git",
            "-c",
            "user.name=AICT Bot",
            "-c",
            "user.email=aict-bot@example.com",
            "commit",
            "-m",
            "init",
        ],
        work,
    )
    _run(["git", "push", "-u", "origin", "main"], work)
    return work, remote


def test_git_service_pr_cycle(tmp_path: Path):
    repo_path, _ = _init_repo(tmp_path)
    service = GitService(str(repo_path))

    service.create_branch(agent_role="engineer", branch_name="feature/test-cycle")
    (repo_path / "feature.txt").write_text("feature work\n", encoding="utf-8")
    commit_sha = service.commit_all("add feature")
    assert len(commit_sha) >= 7

    service.push_branch("feature/test-cycle")
    pr = service.create_pr(
        agent_role="engineer",
        source_branch="feature/test-cycle",
        target_branch="main",
    )
    assert "feature/test-cycle" in pr.pr_url

    merge_sha = service.merge_pr(
        agent_role="cto",
        source_branch="feature/test-cycle",
        target_branch="main",
    )
    assert len(merge_sha) >= 7


def test_git_guardrails_block_main_branch(tmp_path: Path):
    repo_path, _ = _init_repo(tmp_path)
    service = GitService(str(repo_path))
    with pytest.raises(GitOperationBlocked):
        service.create_branch(agent_role="engineer", branch_name="main")


def test_git_guardrails_block_merge_for_engineer(tmp_path: Path):
    repo_path, _ = _init_repo(tmp_path)
    service = GitService(str(repo_path))
    with pytest.raises(GitOperationBlocked):
        service.merge_pr(agent_role="engineer", source_branch="x", target_branch="main")


def test_create_issue_without_github_token(tmp_path: Path):
    """create_issue raises GitOperationFailed when GitHub is not configured."""
    repo_path, _ = _init_repo(tmp_path)
    service = GitService(str(repo_path), github_token=None)
    with pytest.raises(GitOperationFailed, match="GitHub token"):
        service.create_issue(title="Bug: something broke", body="Details here")


def test_create_issue_calls_github_api(tmp_path: Path):
    """create_issue POSTs to GitHub API and returns the response JSON."""
    import httpx
    from unittest.mock import MagicMock, patch

    repo_path, _ = _init_repo(tmp_path)
    # Give the repo a fake github remote so _github_ready returns True
    _run(["git", "remote", "set-url", "origin", "https://github.com/org/repo.git"], repo_path)

    fake_response = MagicMock()
    fake_response.status_code = 201
    fake_response.json.return_value = {
        "number": 42,
        "html_url": "https://github.com/org/repo/issues/42",
        "title": "Bug: something broke",
    }

    with patch("httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.post.return_value = fake_response
        service = GitService(str(repo_path), github_token="fake-token")
        result = service.create_issue(title="Bug: something broke", body="Details here")

    assert result["number"] == 42
    assert "issues/42" in result["html_url"]

