"""
Tests for agent access control.
"""

import pytest

from backend.core.access_control import (
    can_access_spec,
    can_create_pr,
    can_merge_pr,
    can_read_code,
    can_write_code,
    can_write_kanban,
    enforce_code_write,
    enforce_file_read,
    enforce_file_write,
    enforce_git_merge_permission,
    enforce_git_pr_permission,
    enforce_git_ref_write,
    enforce_kanban_write,
    enforce_spec_access,
    is_restricted_branch,
)
from backend.core.exceptions import GitOperationBlocked, ScopeViolationError


class TestSpecAccess:
    def test_manager_can_access_high_level_specs(self):
        assert can_access_spec("manager", "GrandSpecification.tex") is True
        assert can_access_spec("manager", "GrandArchitecture.tex") is True
        assert can_access_spec("manager", "API&Schema.tex") is True

    def test_cto_can_only_access_api_schema(self):
        assert can_access_spec("cto", "API&Schema.tex") is True
        assert can_access_spec("cto", "GrandSpecification.tex") is False

    def test_engineer_cannot_access_specs(self):
        assert can_access_spec("engineer", "API&Schema.tex") is False

    def test_enforce_raises_for_engineer(self):
        with pytest.raises(ScopeViolationError):
            enforce_spec_access("engineer", "API&Schema.tex")


class TestKanbanAccess:
    def test_manager_and_cto_can_write(self):
        assert can_write_kanban("manager") is True
        assert can_write_kanban("cto") is True

    def test_engineer_cannot_write(self):
        assert can_write_kanban("engineer") is False
        with pytest.raises(ScopeViolationError):
            enforce_kanban_write("engineer")


class TestCodeAccess:
    def test_engineer_can_write(self):
        assert can_write_code("engineer") is True
        enforce_code_write("engineer", "src/auth/login.py", "src/auth")

    def test_manager_and_cto_cannot_write(self):
        assert can_write_code("manager") is False
        assert can_write_code("cto") is False

    def test_all_runtime_roles_can_read_code(self):
        assert can_read_code("manager") is True
        assert can_read_code("cto") is True
        assert can_read_code("engineer") is True


class TestGitAccess:
    def test_pr_permissions(self):
        assert can_create_pr("engineer") is True
        assert can_create_pr("manager") is False
        assert can_merge_pr("cto") is True
        assert can_merge_pr("engineer") is False

    def test_branch_guards(self):
        assert is_restricted_branch("main") is True
        assert is_restricted_branch("feature/x") is False

        with pytest.raises(GitOperationBlocked):
            enforce_git_ref_write("engineer", "main")
        with pytest.raises(GitOperationBlocked):
            enforce_git_ref_write("manager", "feature/x")

    def test_permission_enforcers(self):
        enforce_git_pr_permission("engineer")
        with pytest.raises(GitOperationBlocked):
            enforce_git_pr_permission("manager")

        enforce_git_merge_permission("cto")
        with pytest.raises(GitOperationBlocked):
            enforce_git_merge_permission("engineer")


class TestFileAccess:
    SPEC_ROOT = "/repos/specs"
    CODE_ROOT = "/repos/code"

    def test_manager_can_read_grand_spec(self):
        enforce_file_read(
            agent_role="manager",
            absolute_file_path="/repos/specs/GrandSpecification.tex",
            spec_repo_root=self.SPEC_ROOT,
            code_repo_root=self.CODE_ROOT,
        )

    def test_cto_cannot_read_grand_spec(self):
        with pytest.raises(ScopeViolationError):
            enforce_file_read(
                agent_role="cto",
                absolute_file_path="/repos/specs/GrandSpecification.tex",
                spec_repo_root=self.SPEC_ROOT,
                code_repo_root=self.CODE_ROOT,
            )

    def test_engineer_write_scoped_to_module(self):
        enforce_file_write(
            agent_role="engineer",
            absolute_file_path="/repos/code/src/auth/login.py",
            spec_repo_root=self.SPEC_ROOT,
            code_repo_root=self.CODE_ROOT,
            module_path="/repos/code/src/auth",
        )
        with pytest.raises(ScopeViolationError):
            enforce_file_write(
                agent_role="engineer",
                absolute_file_path="/repos/code/src/payments/pay.py",
                spec_repo_root=self.SPEC_ROOT,
                code_repo_root=self.CODE_ROOT,
                module_path="/repos/code/src/auth",
            )
