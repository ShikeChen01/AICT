"""
Tests for Pydantic schemas — validation, defaults, serialization.
"""

import pytest
from pydantic import ValidationError

from backend.schemas.task import TaskCreate, TaskUpdate
from backend.schemas.ticket import TicketCreate
from backend.schemas.chat import ChatMessageCreate
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


# ── TicketCreate ────────────────────────────────────────────────────


class TestTicketCreate:
    def test_defaults(self):
        t = TicketCreate(
            to_agent_id="00000000-0000-0000-0000-000000000001",
            header="Help needed",
            ticket_type="help",
        )
        assert t.critical == 5
        assert t.urgent == 5
        assert t.initial_message is None

    def test_with_message(self):
        t = TicketCreate(
            to_agent_id="00000000-0000-0000-0000-000000000001",
            header="Question",
            ticket_type="question",
            initial_message="What format?",
        )
        assert t.initial_message == "What format?"


# ── ChatMessageCreate ──────────────────────────────────────────────


class TestChatMessageCreate:
    def test_minimal(self):
        m = ChatMessageCreate(content="Hello GM")
        assert m.content == "Hello GM"
        assert m.attachments is None

    def test_with_attachments(self):
        m = ChatMessageCreate(
            content="See attached", attachments=["file1.tex", "file2.tex"]
        )
        assert len(m.attachments) == 2


# ── ProjectCreate ──────────────────────────────────────────────────


class TestProjectCreate:
    def test_minimal(self):
        p = ProjectCreate(name="Test", code_repo_url="https://github.com/x/y")
        assert p.name == "Test"
        assert p.description is None

    def test_full(self):
        p = ProjectCreate(
            name="Full",
            description="A full project",
            code_repo_url="https://github.com/x/y",
        )
        assert p.description == "A full project"
