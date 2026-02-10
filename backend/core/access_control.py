"""
Agent access control.

Enforces which spec files each agent role can read/write,
Kanban access, and code repo scope.
"""

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

    if not file_path.startswith(module_path):
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
