"""
Agent access control.

Enforces role-based permissions for spec/code access and git operations.
"""

from pathlib import PurePosixPath

from backend.core.exceptions import GitOperationBlocked
from backend.core.exceptions import ScopeViolationError

# ── Spec file access ────────────────────────────────────────────────

AGENT_SPEC_ACCESS: dict[str, list[str]] = {
    "gm": [
        "GrandSpecification.tex",
        "GrandArchitecture.tex",
        "API&Schema.tex",
    ],
    "om": [
        "API&Schema.tex",
    ],
    "engineer": [],
}


def can_access_spec(agent_role: str, file_path: str) -> bool:
    """Check if agent role is allowed to access the spec file."""
    allowed = AGENT_SPEC_ACCESS.get(agent_role, [])
    return any(allowed_file in file_path for allowed_file in allowed)


def enforce_spec_access(agent_role: str, file_path: str) -> None:
    """Raise ScopeViolationError if agent cannot access the spec file."""
    if not can_access_spec(agent_role, file_path):
        raise ScopeViolationError(
            f"Agent role '{agent_role}' is not allowed to access '{file_path}'"
        )


# ── Kanban access ───────────────────────────────────────────────────

KANBAN_WRITE_ROLES = ("gm", "om")


def can_write_kanban(agent_role: str) -> bool:
    """GM and OM can write to Kanban; engineers can only read."""
    return agent_role in KANBAN_WRITE_ROLES


def enforce_kanban_write(agent_role: str) -> None:
    """Raise ScopeViolationError if agent cannot write to Kanban."""
    if not can_write_kanban(agent_role):
        raise ScopeViolationError(
            f"Agent role '{agent_role}' does not have write access to Kanban"
        )


# ── Code repo scope ────────────────────────────────────────────────

def can_write_code(agent_role: str) -> bool:
    """Only engineers can write to the code repo."""
    return agent_role == "engineer"


def enforce_code_write(agent_role: str, file_path: str, module_path: str | None) -> None:
    """
    Enforce that engineers can only write within their assigned module_path.
    GM and OM cannot write to the code repo.
    """
    if not can_write_code(agent_role):
        raise ScopeViolationError(
            f"Agent role '{agent_role}' cannot write to the code repo"
        )

    if module_path is None:
        raise ScopeViolationError("Engineer has no assigned module_path")

    if not _is_within(file_path, module_path):
        raise ScopeViolationError(
            f"Engineer can only write within '{module_path}', "
            f"attempted to write to '{file_path}'"
        )


# ── Git PR/Merge access ────────────────────────────────────────────

def can_create_pr(agent_role: str) -> bool:
    """Only engineers create PRs."""
    return agent_role == "engineer"


def can_merge_pr(agent_role: str) -> bool:
    """Only OM can merge PRs."""
    return agent_role == "om"


def _normalize(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def _is_within(path: str, parent: str) -> bool:
    n_path = _normalize(path)
    n_parent = _normalize(parent)
    if n_path == n_parent:
        return True
    return n_path.startswith(n_parent.rstrip("/") + "/")


def can_read_code(agent_role: str) -> bool:
    return agent_role in ("gm", "om", "engineer")


def enforce_code_read(agent_role: str, file_path: str, module_path: str | None) -> None:
    if not can_read_code(agent_role):
        raise ScopeViolationError(f"Agent role '{agent_role}' cannot read code")
    if agent_role == "engineer":
        if module_path is None:
            raise ScopeViolationError("Engineer has no assigned module_path")
        if not _is_within(file_path, module_path):
            raise ScopeViolationError(
                f"Engineer can only read within '{module_path}', attempted '{file_path}'"
            )


def enforce_file_read(
    agent_role: str,
    absolute_file_path: str,
    spec_repo_root: str,
    code_repo_root: str,
    module_path: str | None = None,
) -> None:
    if _is_within(absolute_file_path, spec_repo_root):
        relative = _normalize(absolute_file_path).replace(_normalize(spec_repo_root), "", 1)
        if relative.startswith("/"):
            relative = relative[1:]
        enforce_spec_access(agent_role, relative)
        return
    if _is_within(absolute_file_path, code_repo_root):
        enforce_code_read(agent_role, absolute_file_path, module_path)
        return
    raise ScopeViolationError(f"Path '{absolute_file_path}' is outside allowed repositories")


def enforce_file_write(
    agent_role: str,
    absolute_file_path: str,
    spec_repo_root: str,
    code_repo_root: str,
    module_path: str | None = None,
) -> None:
    if _is_within(absolute_file_path, spec_repo_root):
        relative = _normalize(absolute_file_path).replace(_normalize(spec_repo_root), "", 1)
        if relative.startswith("/"):
            relative = relative[1:]
        enforce_spec_access(agent_role, relative)
        return
    if _is_within(absolute_file_path, code_repo_root):
        enforce_code_write(agent_role, absolute_file_path, module_path)
        return
    raise ScopeViolationError(f"Path '{absolute_file_path}' is outside allowed repositories")


RESTRICTED_BRANCHES = {"main", "master", "develop"}


def is_restricted_branch(branch_name: str) -> bool:
    return branch_name in RESTRICTED_BRANCHES


def enforce_git_ref_write(agent_role: str, branch_name: str) -> None:
    if is_restricted_branch(branch_name):
        raise GitOperationBlocked(f"Direct write to '{branch_name}' branch is blocked")
    if agent_role != "engineer":
        raise GitOperationBlocked(f"Agent role '{agent_role}' cannot write git refs")


def enforce_git_pr_permission(agent_role: str) -> None:
    if not can_create_pr(agent_role):
        raise GitOperationBlocked(f"Agent role '{agent_role}' cannot create pull requests")


def enforce_git_merge_permission(agent_role: str) -> None:
    if not can_merge_pr(agent_role):
        raise GitOperationBlocked(f"Agent role '{agent_role}' cannot merge pull requests")
