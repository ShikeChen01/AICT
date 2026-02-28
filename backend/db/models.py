"""
SQLAlchemy models for AICT.

Target schema per docs/db.md:
- users, repositories, repository_memberships, project_settings, agents, tasks
- channel_messages, agent_messages, agent_sessions, llm_usage_events
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Users ───────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String(128), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    github_token = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    repositories = relationship("Repository", back_populates="owner")
    memberships = relationship("RepositoryMembership", back_populates="user", cascade="all, delete-orphan")


# ── Repositories ────────────────────────────────────────────────────


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    spec_repo_path = Column(String(512), nullable=False)
    code_repo_url = Column(String(512), nullable=False)
    code_repo_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner = relationship("User", back_populates="repositories")
    agents = relationship("Agent", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    project_settings = relationship(
        "ProjectSettings", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    channel_messages = relationship(
        "ChannelMessage", back_populates="project", cascade="all, delete-orphan"
    )
    memberships = relationship(
        "RepositoryMembership", back_populates="repository", cascade="all, delete-orphan"
    )
    documents = relationship(
        "ProjectDocument", back_populates="project", cascade="all, delete-orphan"
    )


# Backwards compatibility
Project = Repository


# ── Repository Memberships ───────────────────────────────────────────


VALID_MEMBERSHIP_ROLES = ("owner", "member", "viewer")


class RepositoryMembership(Base):
    """Tracks which users have access to which repositories and their role."""

    __tablename__ = "repository_memberships"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False, default="member")  # owner | member | viewer
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    repository = relationship("Repository", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        Index("ix_repo_memberships_repo_user", "repository_id", "user_id", unique=True),
        Index("ix_repo_memberships_user", "user_id"),
    )


# ── Project Settings (NEW) ──────────────────────────────────────────


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    max_engineers = Column(Integer, default=5, nullable=False)
    persistent_sandbox_count = Column(Integer, default=1, nullable=False)
    # Phase 3: per-project model and prompt overrides
    model_overrides = Column(JSON, nullable=True)
    prompt_overrides = Column(JSON, nullable=True)
    # Phase 4: hard daily limits
    daily_token_budget = Column(Integer, default=0, nullable=False)
    # Phase 4b: rolling hourly rate limits (0 = unlimited)
    calls_per_hour_limit = Column(Integer, default=0, nullable=False)
    tokens_per_hour_limit = Column(Integer, default=0, nullable=False)
    # Phase 4b: daily cost cap in USD (0.0 = unlimited)
    daily_cost_budget_usd = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="project_settings")


# ── Agents (MODIFIED: memory added, priority removed) ─────────────────


VALID_ROLES = ("manager", "cto", "engineer")
VALID_STATUSES = ("sleeping", "active", "busy")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False)  # 'manager', 'cto', 'engineer'
    display_name = Column(String(100), nullable=False)
    tier = Column(String(50), nullable=True)
    model = Column(String(100), nullable=False)
    status = Column(String(20), default="sleeping", nullable=False)
    current_task_id = Column(
        Uuid,
        ForeignKey("tasks.id", use_alter=True, name="fk_agent_current_task"),
        nullable=True,
    )
    sandbox_id = Column(String(255), nullable=True)
    sandbox_persist = Column(Boolean, default=False, nullable=False)
    memory = Column(JSON, nullable=True)  # Layer 1 self-define block
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="agents")
    current_task = relationship("Task", foreign_keys=[current_task_id])
    agent_sessions = relationship(
        "AgentSession", back_populates="agent", cascade="all, delete-orphan"
    )
    agent_messages = relationship(
        "AgentMessage", back_populates="agent", cascade="all, delete-orphan"
    )


# ── Tasks (MODIFIED: abort fields removed) ───────────────────────────


VALID_TASK_STATUSES = (
    "backlog",
    "specifying",
    "assigned",
    "in_progress",
    "review",
    "done",
    "aborted",
)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="backlog", nullable=False)
    critical = Column(Integer, default=5, nullable=False)
    urgent = Column(Integer, default=5, nullable=False)
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

    project = relationship("Repository", back_populates="tasks")
    assigned_agent = relationship("Agent", foreign_keys=[assigned_agent_id])
    created_by = relationship("Agent", foreign_keys=[created_by_id])
    subtasks = relationship("Task", back_populates="parent_task", foreign_keys=[parent_task_id])
    parent_task = relationship("Task", remote_side=[id], foreign_keys=[parent_task_id])


# ── Channel Messages (NEW) ──────────────────────────────────────────
# from_agent_id / target_agent_id are NOT FKs (user = reserved UUID)


class ChannelMessage(Base):
    __tablename__ = "channel_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id = Column(Uuid, nullable=True)  # NULL = system; user = USER_AGENT_ID
    target_agent_id = Column(Uuid, nullable=True)  # NULL = broadcast
    # Phase 2: real user FK for attribution (set when sent from REST API; NULL for agent-to-agent)
    from_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content = Column(Text, nullable=False)
    message_type = Column(String(20), default="normal", nullable=False)  # 'normal', 'system'
    status = Column(String(20), default="sent", nullable=False)  # 'sent', 'received'
    broadcast = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="channel_messages")
    # Phase 6: linked attachments (selectin avoids N+1 for list queries)
    message_attachments = relationship(
        "MessageAttachment",
        lazy="selectin",
        order_by="MessageAttachment.position",
        cascade="all, delete-orphan",
    )

    @property
    def attachment_ids(self) -> list[str]:
        # Never trigger IO from this property (Pydantic from_attributes calls it in
        # a sync context). Only return IDs when the relationship is already loaded.
        from sqlalchemy import inspect as _sa_inspect
        from sqlalchemy.orm.attributes import NO_VALUE
        try:
            state = _sa_inspect(self)
            if state.expired:
                return []
            loaded = state.attrs.message_attachments.loaded_value
            if loaded is NO_VALUE:
                return []
        except Exception:
            return []
        return [str(ma.attachment_id) for ma in loaded]

    __table_args__ = (
        Index("ix_channel_target_status", "target_agent_id", "status", "created_at"),
        Index("ix_channel_project", "project_id", "created_at"),
    )


# ── Agent Sessions (NEW) ────────────────────────────────────────────


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    trigger_message_id = Column(
        Uuid,
        ForeignKey("channel_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(20), default="running", nullable=False)
    end_reason = Column(String(50), nullable=True)
    iteration_count = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="agent_sessions")
    agent_messages = relationship(
        "AgentMessage", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_agent_sessions_agent", "agent_id", "started_at"),
        Index("ix_agent_sessions_status", "status"),
    )


# ── Agent Messages (NEW) ────────────────────────────────────────────


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        Uuid,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(20), nullable=False)  # 'system', 'user', 'assistant', 'tool'
    content = Column(Text, nullable=False)
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(Text, nullable=True)
    loop_iteration = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    agent = relationship("Agent", back_populates="agent_messages")
    session = relationship("AgentSession", back_populates="agent_messages")

    __table_args__ = (
        Index("ix_agent_messages_agent_time", "agent_id", "created_at"),
        Index("ix_agent_messages_session", "session_id", "loop_iteration"),
    )


# ── LLM Usage Events (Phase 4) ──────────────────────────────────────


class LLMUsageEvent(Base):
    """One row per LLM API call. Used for cost attribution and daily budget enforcement."""

    __tablename__ = "llm_usage_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    session_id = Column(
        Uuid, ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True
    )
    user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider = Column(String(50), nullable=False)   # anthropic | google | openai
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    request_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_llm_usage_project_time", "project_id", "created_at"),
        Index("ix_llm_usage_agent", "agent_id"),
        Index("ix_llm_usage_session", "session_id"),
    )


# ── Phase 6: Attachments ─────────────────────────────────────────────


ALLOWED_ATTACHMENT_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class Attachment(Base):
    """Binary image blob stored directly in Postgres (bytea).

    Capped at 10 MB per file; only image/* MIME types accepted.
    SHA-256 hash stored for integrity checking.
    """

    __tablename__ = "attachments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    message_links = relationship(
        "MessageAttachment", back_populates="attachment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_attachments_project", "project_id", "created_at"),
    )


class MessageAttachment(Base):
    """Junction table: channel_message ↔ attachment (supports multiple images per message)."""

    __tablename__ = "message_attachments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id = Column(
        Uuid, ForeignKey("channel_messages.id", ondelete="CASCADE"), nullable=False
    )
    attachment_id = Column(
        Uuid, ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False
    )
    position = Column(Integer, default=0, nullable=False)

    attachment = relationship("Attachment", back_populates="message_links")

    __table_args__ = (
        Index("ix_msg_attachments_message", "message_id"),
        Index("ix_msg_attachments_attachment", "attachment_id"),
    )


# ── Phase 10: Project Documents ──────────────────────────────────────


class ProjectDocument(Base):
    """Manager-agent-writable architecture document. Read-only for users via REST.

    Well-known doc_type values:
      'architecture_source_of_truth' — single canonical architecture description
      'arc42_lite'                   — arc42-lite template content
      'c4_diagrams'                  — C4 model diagrams (Markdown + PlantUML/Mermaid)
      'adr/<slug>'                   — individual Architecture Decision Records
    """

    __tablename__ = "project_documents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    doc_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    updated_by_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="documents")
    updated_by_agent = relationship("Agent", foreign_keys=[updated_by_agent_id])

    __table_args__ = (
        Index("ix_project_documents_project", "project_id", "updated_at"),
        # unique constraint handled at migration level
    )
