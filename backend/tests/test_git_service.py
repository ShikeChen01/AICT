import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# ── create_issue tests ────────────────────────────────────────────────────────


def test_create_issue_no_token_raises(tmp_path: Path):
    """create_issue raises GitOperationFailed when no GitHub token is set."""
    service = GitService(str(tmp_path), github_token=None)
    # Patch settings so github_token is also None
    with patch("backend.services.git_service.settings") as mock_settings:
        mock_settings.github_token = None
        mock_settings.github_api_base_url = "https://api.github.com"
        service.github_token = None
        with pytest.raises(GitOperationFailed, match="GitHub token"):
            service.create_issue(title="Test issue")


def test_create_issue_no_remote_raises(tmp_path: Path):
    """create_issue raises GitOperationFailed when repo has no GitHub remote."""
    # tmp_path has no git remote
    service = GitService(str(tmp_path), github_token="fake-token")
    with pytest.raises(GitOperationFailed, match="No GitHub remote"):
        service.create_issue(title="Test issue")


def test_create_issue_success(tmp_path: Path):
    """create_issue calls GitHub API and returns issue data on 201."""
    service = GitService(str(tmp_path), github_token="fake-token")
    fake_response = {"html_url": "https://github.com/owner/repo/issues/1", "number": 1}

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = fake_response

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    # Patch _github_ready to return a valid slug
    with patch.object(service, "_github_ready", return_value=(True, "owner/repo")):
        with patch("backend.services.git_service.httpx.Client", return_value=mock_client):
            result = service.create_issue(
                title="Test issue", body="Body text", labels=["bug"], assignees=["alice"]
            )

    assert result["html_url"] == "https://github.com/owner/repo/issues/1"
    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["title"] == "Test issue"
    assert payload["labels"] == ["bug"]
    assert payload["assignees"] == ["alice"]


def test_create_issue_api_failure_raises(tmp_path: Path):
    """create_issue raises GitOperationFailed on non-201 response."""
    service = GitService(str(tmp_path), github_token="fake-token")

    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = "Unprocessable Entity"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch.object(service, "_github_ready", return_value=(True, "owner/repo")):
        with patch("backend.services.git_service.httpx.Client", return_value=mock_client):
            with pytest.raises(GitOperationFailed, match="issue creation failed"):
                service.create_issue(title="Bad issue")


# ── create_github_project tests ───────────────────────────────────────────────


def test_create_github_project_no_token_raises(tmp_path: Path):
    """create_github_project raises GitOperationFailed when no GitHub token is set."""
    service = GitService(str(tmp_path), github_token=None)
    with patch("backend.services.git_service.settings") as mock_settings:
        mock_settings.github_token = None
        mock_settings.github_api_base_url = "https://api.github.com"
        service.github_token = None
        with pytest.raises(GitOperationFailed, match="GitHub token"):
            service.create_github_project(name="My Project")


def test_create_github_project_no_remote_raises(tmp_path: Path):
    """create_github_project raises GitOperationFailed when repo has no GitHub remote."""
    service = GitService(str(tmp_path), github_token="fake-token")
    with pytest.raises(GitOperationFailed, match="No GitHub remote"):
        service.create_github_project(name="My Project")


def test_create_github_project_success(tmp_path: Path):
    """create_github_project calls GitHub API and returns project data on 201."""
    service = GitService(str(tmp_path), github_token="fake-token")
    fake_response = {"html_url": "https://github.com/owner/repo/projects/1", "id": 1}

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = fake_response

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch.object(service, "_github_ready", return_value=(True, "owner/repo")):
        with patch("backend.services.git_service.httpx.Client", return_value=mock_client):
            result = service.create_github_project(name="Sprint 1", body="First sprint")

    assert result["html_url"] == "https://github.com/owner/repo/projects/1"
    _, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["name"] == "Sprint 1"
    assert payload["body"] == "First sprint"


def test_create_github_project_api_failure_raises(tmp_path: Path):
    """create_github_project raises GitOperationFailed on non-201 response."""
    service = GitService(str(tmp_path), github_token="fake-token")

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch.object(service, "_github_ready", return_value=(True, "owner/repo")):
        with patch("backend.services.git_service.httpx.Client", return_value=mock_client):
            with pytest.raises(GitOperationFailed, match="project creation failed"):
                service.create_github_project(name="Blocked Project")


