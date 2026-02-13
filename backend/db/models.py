"""
SQLAlchemy models for AICT MVP-0.

6 tables:
- projects: single project config
- agents: Manager, Engineers (max 5 engineers enforced in code)
- tasks: Kanban cards with 2D priority (critical + urgent)
- tickets: agent-to-agent communication queue
- ticket_messages: conversation within a ticket
- chat_messages: user <-> Manager conversation
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    event,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Projects ────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    spec_repo_path = Column(String(512), nullable=False)
    code_repo_url = Column(String(512), nullable=False)
    code_repo_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    agents = relationship("Agent", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="project", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="project", cascade="all, delete-orphan")


# ── Agents ──────────────────────────────────────────────────────────

VALID_ROLES = ("gm", "om", "manager", "engineer")
VALID_STATUSES = ("sleeping", "active", "busy")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False)  # 'manager', 'engineer' (gm/om deprecated)
    display_name = Column(String(100), nullable=False)  # e.g. 'Manager', 'Engineer-3'
    model = Column(String(100), nullable=False)  # e.g. 'gemini-3-pro', 'claude-4.5-opus'
    status = Column(String(20), default="sleeping", nullable=False)
    current_task_id = Column(Uuid, ForeignKey("tasks.id"), nullable=True)
    sandbox_id = Column(String(255), nullable=True)
    sandbox_persist = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=2, nullable=False)  # 0=Manager, 1=Engineer
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    project = relationship("Project", back_populates="agents")
    current_task = relationship("Task", foreign_keys=[current_task_id])


# ── Tasks (Kanban cards) ───────────────────────────────────────────

VALID_TASK_STATUSES = (
    "backlog",
    "specifying",
    "assigned",
    "in_progress",
    "in_review",
    "done",
)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="backlog", nullable=False)
    critical = Column(Integer, default=5, nullable=False)  # 0-10, 0=most critical
    urgent = Column(Integer, default=5, nullable=False)  # 0-10, 0=most urgent
    assigned_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    module_path = Column(String(512), nullable=True)
    git_branch = Column(String(255), nullable=True)
    pr_url = Column(String(512), nullable=True)
    parent_task_id = Column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    project = relationship("Project", back_populates="tasks")
    assigned_agent = relationship("Agent", foreign_keys=[assigned_agent_id])
    created_by = relationship("Agent", foreign_keys=[created_by_id])
    subtasks = relationship("Task", back_populates="parent_task", foreign_keys=[parent_task_id])
    parent_task = relationship("Task", remote_side=[id], foreign_keys=[parent_task_id])


# ── Tickets ─────────────────────────────────────────────────────────

VALID_TICKET_TYPES = ("task_assignment", "question", "help", "issue")
VALID_TICKET_STATUSES = ("open", "closed")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    to_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    header = Column(String(255), nullable=False)
    ticket_type = Column(String(50), nullable=False)
    critical = Column(Integer, default=5, nullable=False)
    urgent = Column(Integer, default=5, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    # relationships
    project = relationship("Project", back_populates="tickets")
    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    to_agent = relationship("Agent", foreign_keys=[to_agent_id])
    closed_by = relationship("Agent", foreign_keys=[closed_by_id])
    messages = relationship(
        "TicketMessage", back_populates="ticket", cascade="all, delete-orphan"
    )


# ── Ticket Messages ────────────────────────────────────────────────

class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_id = Column(
        Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # relationships
    ticket = relationship("Ticket", back_populates="messages")
    from_agent = relationship("Agent")


# ── Chat Messages ──────────────────────────────────────────────────

VALID_CHAT_ROLES = ("user", "gm", "manager")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(20), nullable=False)  # 'user', 'manager' ('gm' deprecated)
    content = Column(Text, nullable=False)
    attachments = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # relationships
    project = relationship("Project", back_populates="chat_messages")
