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
    BigInteger,
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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from sqlalchemy.types import TypeDecorator


class _VectorType(TypeDecorator):
    """Dialect-aware vector column: pgvector VECTOR on PostgreSQL, TEXT on SQLite."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 1024) -> None:
        super().__init__()
        self._dim = dim
        try:
            from pgvector.sqlalchemy import Vector as _PgVector  # type: ignore[import-untyped]
            self._pg_type = _PgVector(dim)
        except ImportError:
            self._pg_type = None

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and self._pg_type is not None:
            return dialect.type_descriptor(self._pg_type)
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "postgresql":
            import json
            return json.dumps(value if isinstance(value, list) else list(value))
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "postgresql" and isinstance(value, str):
            import json
            return json.loads(value)
        return value


_VECTOR_1024 = _VectorType(1024)


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
    sandbox_configs = relationship("SandboxConfig", back_populates="user", cascade="all, delete-orphan")


# ── Sandbox Configs ────────────────────────────────────────────────


class SandboxConfig(Base):
    """User-level sandbox configuration profile.

    Stores a setup script (shell commands) that runs inside a sandbox container
    after creation.  Users create configs (e.g. "Chrome + Slack + VS Code")
    and assign them to agents.  Configs are user-owned and reusable across
    projects.
    """

    __tablename__ = "sandbox_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    setup_script = Column(Text, nullable=False, default="")
    os_image = Column(String(50), nullable=True)  # e.g. "ubuntu-22.04", "windows-server-2022"
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="sandbox_configs")
    agents = relationship("Agent", back_populates="sandbox_config")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_sandbox_configs_user_name"),
    )


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
    agent_templates = relationship("AgentTemplate", back_populates="project", cascade="all, delete-orphan")
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
    project_secrets = relationship(
        "ProjectSecret", back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_documents = relationship(
        "KnowledgeDocument", back_populates="project", cascade="all, delete-orphan"
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
    # Phase 1.6: RAG knowledge base quotas (0 = unlimited)
    knowledge_max_documents = Column(Integer, default=50, nullable=False)
    knowledge_max_total_bytes = Column(BigInteger, default=100 * 1024 * 1024, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="project_settings")


# ── Project Secrets ──────────────────────────────────────────────────


class ProjectSecret(Base):
    """Per-project secret tokens (e.g. API keys) for agent use. Values stored encrypted."""

    __tablename__ = "project_secrets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    hint = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="project_secrets")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_secrets_project_name"),)


# ── Agents (MODIFIED: memory added, priority removed) ─────────────────


# System roles (backwards-compat) plus "worker" for user-defined agents.
# Any string is accepted in the DB; this tuple is only for display/sort ordering.
VALID_ROLES = ("manager", "cto", "engineer", "worker")
VALID_STATUSES = ("sleeping", "active", "busy")

# ── Agent Templates ──────────────────────────────────────────────────

VALID_BASE_ROLES = ("manager", "cto", "worker", "custom")


class AgentTemplate(Base):
    """Reusable agent design/configuration. DB is source of truth.

    System defaults (Manager, CTO, Engineer) are created automatically per project.
    Users can create custom agent designs with any role, prompt, tools, and sandbox
    configuration.  This serves as the "Agent Designer" concept in the product.
    Template changes only affect newly created agents; existing agents keep their values.
    """

    __tablename__ = "agent_templates"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)  # Human-readable description
    base_role = Column(String(50), nullable=False)  # 'manager', 'cto', 'worker', or any custom string
    model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=True)  # NULL = infer from model name
    thinking_enabled = Column(Boolean, default=False, nullable=False)
    tool_access = Column(JSON, nullable=True)  # Future: custom tool whitelist
    sandbox_template = Column(String(100), nullable=True)  # e.g. "dev-python", "browser-automation"
    knowledge_sources = Column(JSON, nullable=True)  # RAG config: {sources: [...], shared_access: "read"|"write"|"both"}
    trigger_config = Column(JSON, nullable=True)  # Trigger config: {type: "message"|"schedule"|"event", ...}
    cost_limits = Column(JSON, nullable=True)  # {max_tokens_per_session, max_cost_per_session_usd, ...}
    is_system_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="agent_templates")
    agents = relationship("Agent", back_populates="template")
    prompt_blocks = relationship(
        "PromptBlockConfig",
        primaryjoin="AgentTemplate.id == PromptBlockConfig.template_id",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    tool_configs = relationship(
        "ToolConfig",
        primaryjoin="AgentTemplate.id == ToolConfig.template_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_templates_project", "project_id"),
    )


class PromptBlockConfig(Base):
    """Per-agent or per-template prompt block configuration.

    DB is always the source of truth. Seeded from .md files at template/agent creation.
    Exactly one of template_id or agent_id must be set.
    The 'content' column is always populated (never NULL after seeding).
    Duplication is supported: multiple rows with same block_key but different position.
    """

    __tablename__ = "prompt_block_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id = Column(
        Uuid, ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True
    )
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    block_key = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    template = relationship(
        "AgentTemplate",
        foreign_keys=[template_id],
        back_populates="prompt_blocks",
    )
    agent = relationship(
        "Agent",
        foreign_keys=[agent_id],
        back_populates="prompt_blocks",
    )

    __table_args__ = (
        Index("ix_prompt_block_configs_template", "template_id", "position"),
        Index("ix_prompt_block_configs_agent", "agent_id", "position"),
    )


class ToolConfig(Base):
    """Per-agent or per-template tool configuration.

    DB is the source of truth. Seeded from tool_descriptions.json at agent creation.
    Exactly one of template_id or agent_id must be set.
    Users can edit: description, detailed_description, enabled, position.
    Users cannot edit: tool_name, input_schema, allowed_roles (structural).
    """

    __tablename__ = "tool_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id = Column(
        Uuid, ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True
    )
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    tool_name = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    detailed_description = Column(Text, nullable=True)
    input_schema = Column(JSON, nullable=False)
    allowed_roles = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, default=True, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_tool_configs_agent", "agent_id", "position"),
        Index("ix_tool_configs_template", "template_id", "position"),
    )


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    template_id = Column(
        Uuid, ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True
    )
    role = Column(String(50), nullable=False)  # 'manager', 'cto', 'engineer'
    display_name = Column(String(100), nullable=False)
    tier = Column(String(50), nullable=True)  # deprecated; use template.name
    model = Column(String(100), nullable=False)  # always populated; DB is source of truth
    provider = Column(String(50), nullable=True)  # explicit provider; populated at creation
    thinking_enabled = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="sleeping", nullable=False)
    current_task_id = Column(
        Uuid,
        ForeignKey("tasks.id", use_alter=True, name="fk_agent_current_task"),
        nullable=True,
    )
    sandbox_id = Column(String(255), nullable=True)
    sandbox_persist = Column(Boolean, default=False, nullable=False)
    sandbox_config_id = Column(
        Uuid, ForeignKey("sandbox_configs.id", ondelete="SET NULL"), nullable=True
    )
    memory = Column(JSON, nullable=True)  # Layer 1 self-define block
    # Per-agent dynamic pool overrides. NULL = use system defaults.
    # Shape: {incoming_msg_tokens, memory_pct, past_session_pct, current_session_pct}
    token_allocations = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="agents")
    template = relationship("AgentTemplate", back_populates="agents", foreign_keys=[template_id])
    sandbox_config = relationship("SandboxConfig", back_populates="agents")
    current_task = relationship("Task", foreign_keys=[current_task_id])
    agent_sessions = relationship(
        "AgentSession", back_populates="agent", cascade="all, delete-orphan"
    )
    agent_messages = relationship(
        "AgentMessage", back_populates="agent", cascade="all, delete-orphan"
    )
    prompt_blocks = relationship(
        "PromptBlockConfig",
        primaryjoin="Agent.id == PromptBlockConfig.agent_id",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    tool_configs = relationship(
        "ToolConfig",
        primaryjoin="Agent.id == ToolConfig.agent_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agents_project_status", "project_id", "status"),
        Index("ix_agents_project_role", "project_id", "role"),
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

    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
    )


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
    """Architecture document. Writable by both users and the manager agent.

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
    updated_by_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    current_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="documents")
    updated_by_agent = relationship("Agent", foreign_keys=[updated_by_agent_id])
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id])
    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )

    __table_args__ = (
        Index("ix_project_documents_project", "project_id", "updated_at"),
        # unique constraint handled at migration level
    )


class DocumentVersion(Base):
    """Version snapshot of a project document.

    Created before every edit (by user or agent). Keeps last N=20 versions per document.
    Revert creates a new version rather than destructive rollback.
    """

    __tablename__ = "document_versions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(
        Uuid, ForeignKey("project_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    title = Column(String(255), nullable=True)
    edited_by_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    edited_by_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edit_summary = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    document = relationship("ProjectDocument", back_populates="versions")
    edited_by_agent = relationship("Agent", foreign_keys=[edited_by_agent_id])
    edited_by_user = relationship("User", foreign_keys=[edited_by_user_id])

    __table_args__ = (
        Index("ix_document_versions_doc_num", "document_id", "version_number", unique=True),
        Index("ix_document_versions_doc_time", "document_id", "created_at"),
    )


# ── Knowledge Base (RAG — Feature 1.6) ──────────────────────────────

# Valid file types accepted by the ingestion pipeline
KNOWLEDGE_VALID_FILE_TYPES = frozenset({"pdf", "txt", "markdown", "csv"})
KNOWLEDGE_VALID_STATUSES = frozenset({"pending", "indexing", "indexed", "failed"})


class KnowledgeDocument(Base):
    """An uploaded document in the project's RAG knowledge base.

    After upload, the ingestion pipeline parses, chunks, and embeds the document.
    Once status == 'indexed', agents can search its content via the
    search_knowledge tool.
    """

    __tablename__ = "knowledge_documents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)   # pdf | txt | markdown | csv
    mime_type = Column(String(100), nullable=False)
    original_size_bytes = Column(Integer, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Repository", back_populates="knowledge_documents")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])
    chunks = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_documents_project_created", "project_id", "created_at"),
        Index("ix_knowledge_documents_project_status", "project_id", "status"),
    )


class KnowledgeChunk(Base):
    """A chunked excerpt from a KnowledgeDocument, stored with its embedding.

    The embedding column holds a 1024-dimension float vector produced by
    Voyage AI (voyage-3-large).  pgvector HNSW index on the embedding column
    enables sub-millisecond cosine-similarity search.
    """

    __tablename__ = "knowledge_chunks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(
        Uuid, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    # Voyage-3-large produces 1024-dim vectors
    embedding = Column(_VECTOR_1024, nullable=True)
    # Extra metadata: page_num, char_offset, section_title, …
    metadata_ = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    document = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        Index("ix_knowledge_chunks_doc_idx", "document_id", "chunk_index", unique=True),
        Index("ix_knowledge_chunks_project", "project_id", "created_at"),
        # NOTE: the HNSW vector index is created via raw DDL in migration 024
        # because Alembic cannot render CREATE INDEX … USING hnsw natively.
    )
