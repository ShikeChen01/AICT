"""
Tests for agent access control.
"""

import pytest

from backend.core.access_control import (
    can_access_spec,
    can_create_pr,
    can_merge_pr,
    can_write_code,
    can_write_kanban,
    enforce_code_write,
    enforce_kanban_write,
    enforce_spec_access,
)
from backend.core.exceptions import ScopeViolationError


# ── Spec file access ────────────────────────────────────────────────


class TestSpecAccess:
    def test_gm_can_access_grand_spec(self):
        assert can_access_spec("gm", "GrandSpecification.tex") is True

    def test_gm_can_access_grand_arch(self):
        assert can_access_spec("gm", "GrandArchitecture.tex") is True

    def test_gm_can_access_api_schema(self):
        assert can_access_spec("gm", "API&Schema.tex") is True

    def test_gm_can_access_nested_path(self):
        assert can_access_spec("gm", "specs/GrandSpecification.tex") is True

    def test_om_can_access_api_schema(self):
        assert can_access_spec("om", "API&Schema.tex") is True

    def test_om_cannot_access_grand_spec(self):
        assert can_access_spec("om", "GrandSpecification.tex") is False

    def test_om_cannot_access_grand_arch(self):
        assert can_access_spec("om", "GrandArchitecture.tex") is False

    def test_engineer_cannot_access_any_spec(self):
        assert can_access_spec("engineer", "GrandSpecification.tex") is False
        assert can_access_spec("engineer", "GrandArchitecture.tex") is False
        assert can_access_spec("engineer", "API&Schema.tex") is False

    def test_unknown_role_cannot_access(self):
        assert can_access_spec("unknown", "GrandSpecification.tex") is False

    def test_enforce_raises_for_engineer(self):
        with pytest.raises(ScopeViolationError):
            enforce_spec_access("engineer", "API&Schema.tex")

    def test_enforce_passes_for_gm(self):
        enforce_spec_access("gm", "API&Schema.tex")  # should not raise

    def test_enforce_raises_for_om_on_grand_spec(self):
        with pytest.raises(ScopeViolationError):
            enforce_spec_access("om", "GrandSpecification.tex")


# ── Kanban access ───────────────────────────────────────────────────


class TestKanbanAccess:
    def test_gm_can_write(self):
        assert can_write_kanban("gm") is True

    def test_om_can_write(self):
        assert can_write_kanban("om") is True

    def test_engineer_cannot_write(self):
        assert can_write_kanban("engineer") is False

    def test_enforce_raises_for_engineer(self):
        with pytest.raises(ScopeViolationError):
            enforce_kanban_write("engineer")

    def test_enforce_passes_for_gm(self):
        enforce_kanban_write("gm")  # should not raise


# ── Code repo access ───────────────────────────────────────────────


class TestCodeAccess:
    def test_engineer_can_write(self):
        assert can_write_code("engineer") is True

    def test_gm_cannot_write(self):
        assert can_write_code("gm") is False

    def test_om_cannot_write(self):
        assert can_write_code("om") is False

    def test_enforce_within_module_path(self):
        enforce_code_write("engineer", "src/auth/login.py", "src/auth")
        # should not raise

    def test_enforce_outside_module_path(self):
        with pytest.raises(ScopeViolationError):
            enforce_code_write("engineer", "src/payments/pay.py", "src/auth")

    def test_enforce_no_module_path(self):
        with pytest.raises(ScopeViolationError):
            enforce_code_write("engineer", "src/auth/login.py", None)

    def test_enforce_gm_cannot_write_code(self):
        with pytest.raises(ScopeViolationError):
            enforce_code_write("gm", "src/auth/login.py", "src/auth")


# ── Git PR/Merge access ────────────────────────────────────────────


class TestGitAccess:
    def test_engineer_can_create_pr(self):
        assert can_create_pr("engineer") is True

    def test_gm_cannot_create_pr(self):
        assert can_create_pr("gm") is False

    def test_om_cannot_create_pr(self):
        assert can_create_pr("om") is False

    def test_om_can_merge_pr(self):
        assert can_merge_pr("om") is True

    def test_engineer_cannot_merge_pr(self):
        assert can_merge_pr("engineer") is False

    def test_gm_cannot_merge_pr(self):
        assert can_merge_pr("gm") is False
