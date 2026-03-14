"""
Tests for Pydantic schemas — validation, defaults, serialization.
"""

import pytest
from pydantic import ValidationError

from backend.schemas.task import TaskCreate, TaskUpdate
from backend.schemas.project import ProjectCreate


# ── TaskCreate ──────────────────────────────────────────────────────


class TestTaskCreate:
    def test_minimal(self):
        t = TaskCreate(title="Do something")
        assert t.title == "Do something"
        assert t.status == "backlog"
        assert t.critical == 5
        assert t.urgent == 5
        assert t.description is None
        assert t.module_path is None
        assert t.parent_task_id is None

    def test_full(self):
        t = TaskCreate(
            title="Auth",
            description="Build login",
            status="specifying",
            critical=0,
            urgent=1,
            module_path="src/auth",
        )
        assert t.critical == 0
        assert t.urgent == 1

    def test_critical_out_of_range(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="Bad", critical=11)

    def test_urgent_out_of_range(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="Bad", urgent=-1)


# ── TaskUpdate ──────────────────────────────────────────────────────


class TestTaskUpdate:
    def test_all_none_by_default(self):
        t = TaskUpdate()
        assert t.title is None
        assert t.status is None
        assert t.critical is None

    def test_partial_update(self):
        t = TaskUpdate(status="in_progress", critical=2)
        assert t.status == "in_progress"
        assert t.critical == 2
        assert t.title is None

    def test_exclude_unset(self):
        t = TaskUpdate(status="done")
        data = t.model_dump(exclude_unset=True)
        assert "status" in data
        assert "title" not in data


# TicketCreate removed (tickets deprecated, docs-first)


# ── ProjectCreate ──────────────────────────────────────────────────


class TestProjectCreate:
    def test_minimal_without_repo(self):
        p = ProjectCreate(name="Test")
        assert p.name == "Test"
        assert p.description is None
        assert p.code_repo_url is None

    def test_minimal_with_repo(self):
        p = ProjectCreate(name="Test", code_repo_url="https://github.com/x/y")
        assert p.name == "Test"
        assert p.description is None
        assert p.code_repo_url == "https://github.com/x/y"

    def test_full(self):
        p = ProjectCreate(
            name="Full",
            description="A full project",
            code_repo_url="https://github.com/x/y",
        )
        assert p.description == "A full project"
        assert p.code_repo_url == "https://github.com/x/y"
