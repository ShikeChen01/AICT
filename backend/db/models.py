"""
SQLAlchemy models for AICT.

Central schema:
  projects, users, project_memberships, project_settings, project_secrets
  agents, agent_templates, tasks
  sandbox_configs, sandboxes, sandbox_snapshots, sandbox_usage_events
  channel_messages, agent_sessions, agent_messages
  llm_usage_events, attachments, message_attachments
  project_documents, document_versions
  knowledge_documents, knowledge_chunks
  mcp_server_configs, prompt_block_configs, tool_configs
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

    projects = relationship("Project", back_populates="owner")
    memberships = relationship("ProjectMembership", back_populates="user", cascade="all, delete-orphan")
    sandbox_configs = relationship("SandboxConfig", back_populates="user", cascade="all, delete-orphan")


# ── Sandbox Configs (user-owned blueprints) ────────────────────────


class SandboxConfig(Base):
    """User-level sandbox configuration blueprint.

    Stores a setup script (shell commands) that runs inside a sandbox container
    after creation.  Users create configs (e.g. "Chrome + Slack + VS Code")
    and assign them to sandboxes.  Configs are user-owned and reusable across
    projects.  The ``persistent`` flag indicates whether sandboxes created from
    this config should survive across agent runs.
    """

    __tablename__ = "sandbox_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    os_image = Column(String(100), nullable=False, default="ubuntu-22.04")
    setup_script = Column(Text, nullable=False, default="")
    persistent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="sandbox_configs")
    sandboxes = relationship("Sandbox", back_populates="config")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_sandbox_configs_user_name"),
    )


# ── Sandboxes (runtime instances) ──────────────────────────────────


class Sandbox(Base):
    """Runtime sandbox instance.

    Tracks the lifecycle of a sandbox container from provisioning to release.
    Created from a SandboxConfig blueprint — runtime state only; no duplication
    of config fields.  Can be assigned to an agent or left in a pool.
    """

    __tablename__ = "sandboxes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    sandbox_config_id = Column(Uuid, ForeignKey("sandbox_configs.id", ondelete="SET NULL"), nullable=True)

    orchestrator_sandbox_id = Column(String(255), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="provisioning")
    host = Column(String(255), nullable=True)
    port = Column(Integer, default=8080)
    auth_token = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    last_health_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")
    agent = relationship("Agent", back_populates="sandbox")
    config = relationship("SandboxConfig", back_populates="sandboxes")
    snapshots = relationship("SandboxSnapshot", back_populates="sandbox", cascade="all, delete-orphan")


class SandboxSnapshot(Base):
    """Point-in-time capture of a sandbox for rollback/restore."""

    __tablename__ = "sandbox_snapshots"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    sandbox_id = Column(Uuid, ForeignKey("sandboxes.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    k8s_snapshot_name = Column(String(255), nullable=False)
    os_image = Column(String(100), nullable=False)
    label = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    sandbox = relationship("Sandbox", back_populates="snapshots")


class SandboxUsageEvent(Base):
    """Cost tracking event for sandbox pod utilization."""

    __tablename__ = "sandbox_usage_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    sandbox_id = Column(Uuid, ForeignKey("sandboxes.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False)
    pod_seconds = Column(Float, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


# ── Projects ───────────────────────────────────────────────────────


class Project(Base):
    __tablename__ = "projects"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    spec_repo_path = Column(String(512), nullable=False)
    code_repo_url = Column(String(512), nullable=False)
    code_repo_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner = relationship("User", back_populates="projects")
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
        "ProjectMembership", back_populates="project", cascade="all, delete-orphan"
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


# Backwards compatibility alias — service layer uses both names.
Repository = Project


# ── Project Memberships ─────────────────────────────────────────────


VALID_MEMBERSHIP_ROLES = ("owner", "member", "viewer")


class ProjectMembership(Base):
    """Tracks which users have access to which projects and their role."""

    __tablename__ = "project_memberships"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False, default="member")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    project = relationship("Project", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        Index("ix_project_memberships_project_user", "project_id", "user_id", unique=True),
        Index("ix_project_memberships_user", "user_id"),
    )


# ── Project Settings ────────────────────────────────────────────────


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    max_engineers = Column(Integer, default=5, nullable=False)
    persistent_sandbox_count = Column(Integer, default=1, nullable=False)
    model_overrides = Column(JSON, nullable=True)
    prompt_overrides = Column(JSON, nullable=True)
    daily_token_budget = Column(Integer, default=0, nullable=False)
    calls_per_hour_limit = Column(Integer, default=0, nullable=False)
    tokens_per_hour_limit = Column(Integer, default=0, nullable=False)
    daily_cost_budget_usd = Column(Float, default=0.0, nullable=False)
    knowledge_max_documents = Column(Integer, default=50, nullable=False)
    knowledge_max_total_bytes = Column(BigInteger, default=100 * 1024 * 1024, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Project", back_populates="project_settings")


# ── Project Secrets ─────────────────────────────────────────────────


class ProjectSecret(Base):
    """Per-project encrypted secret tokens (e.g. API keys) for agent use."""

    __tablename__ = "project_secrets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    hint = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Project", back_populates="project_secrets")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_secrets_project_name"),)


# ── Agent Templates ─────────────────────────────────────────────────


VALID_BASE_ROLES = ("manager", "cto", "worker", "custom")


class AgentTemplate(Base):
    """Reusable agent design/configuration.

    System defaults (Manager, CTO, Engineer) are created automatically per
    project.  Users can create custom agent designs with any role, prompt,
    tools, and sandbox configuration.  Template changes only affect newly
    created agents; existing agents keep their snapshot values.
    """

    __tablename__ = "agent_templates"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    base_role = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=True)
    thinking_enabled = Column(Boolean, default=False, nullable=False)
    tool_access = Column(JSON, nullable=True)
    sandbox_template = Column(String(100), nullable=True)
    knowledge_sources = Column(JSON, nullable=True)
    trigger_config = Column(JSON, nullable=True)
    cost_limits = Column(JSON, nullable=True)
    is_system_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Project", back_populates="agent_templates")
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


# ── Prompt Block Configs ────────────────────────────────────────────


class PromptBlockConfig(Base):
    """Per-agent or per-template prompt block configuration.

    Exactly one of template_id or agent_id must be set.
    Content is always populated after seeding.
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

    template = relationship("AgentTemplate", foreign_keys=[template_id], back_populates="prompt_blocks")
    agent = relationship("Agent", foreign_keys=[agent_id], back_populates="prompt_blocks")

    __table_args__ = (
        Index("ix_prompt_block_configs_template", "template_id", "position"),
        Index("ix_prompt_block_configs_agent", "agent_id", "position"),
    )


# ── MCP Server Configs ──────────────────────────────────────────────


class McpServerConfig(Base):
    """Per-agent MCP server connection.

    Each row represents one remote MCP server that an agent can reach.
    Tools exposed by the server are discovered at runtime via tools/list
    and injected into the agent's tool registry.
    """

    __tablename__ = "mcp_server_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(120), nullable=False)
    url = Column(Text, nullable=False)
    api_key = Column(LargeBinary, nullable=True)
    headers = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    status = Column(String(30), default="disconnected", nullable=False)
    status_detail = Column(Text, nullable=True)
    tool_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_mcp_server_configs_agent", "agent_id"),
    )


# ── Tool Configs ────────────────────────────────────────────────────


class ToolConfig(Base):
    """Per-agent or per-template tool configuration.

    Exactly one of template_id or agent_id must be set.
    source: 'native' (from tool_descriptions.json) or 'mcp' (discovered).
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
    source = Column(String(20), default="native", nullable=False)
    mcp_server_id = Column(
        Uuid, ForeignKey("mcp_server_configs.id", ondelete="CASCADE"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_tool_configs_agent", "agent_id", "position"),
        Index("ix_tool_configs_template", "template_id", "position"),
        Index("ix_tool_configs_mcp_server", "mcp_server_id"),
    )


# ── Agents ──────────────────────────────────────────────────────────


VALID_ROLES = ("manager", "cto", "engineer", "worker")
VALID_STATUSES = ("sleeping", "active", "busy")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    template_id = Column(
        Uuid, ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True
    )
    role = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=True)
    thinking_enabled = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="sleeping", nullable=False)
    current_task_id = Column(
        Uuid,
        ForeignKey("tasks.id", use_alter=True, name="fk_agent_current_task"),
        nullable=True,
    )
    memory = Column(JSON, nullable=True)
    token_allocations = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Project", back_populates="agents")
    template = relationship("AgentTemplate", back_populates="agents", foreign_keys=[template_id])
    sandbox = relationship("Sandbox", back_populates="agent", uselist=False)
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


# ── Tasks ───────────────────────────────────────────────────────────


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
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
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

    project = relationship("Project", back_populates="tasks")
    assigned_agent = relationship("Agent", foreign_keys=[assigned_agent_id])
    created_by = relationship("Agent", foreign_keys=[created_by_id])
    subtasks = relationship("Task", back_populates="parent_task", foreign_keys=[parent_task_id])
    parent_task = relationship("Task", remote_side=[id], foreign_keys=[parent_task_id])

    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
    )


# ── Channel Messages ───────────────────────────────────────────────


class ChannelMessage(Base):
    __tablename__ = "channel_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    target_agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    from_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content = Column(Text, nullable=False)
    message_type = Column(String(20), default="normal", nullable=False)
    status = Column(String(20), default="sent", nullable=False)
    broadcast = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    project = relationship("Project", back_populates="channel_messages")
    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    target_agent = relationship("Agent", foreign_keys=[target_agent_id])
    message_attachments = relationship(
        "MessageAttachment",
        lazy="selectin",
        order_by="MessageAttachment.position",
        cascade="all, delete-orphan",
    )

    @property
    def attachment_ids(self) -> list[str]:
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


# ── Agent Sessions ──────────────────────────────────────────────────


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    trigger_message_id = Column(
        Uuid, ForeignKey("channel_messages.id", ondelete="SET NULL"), nullable=True
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


# ── Agent Messages ──────────────────────────────────────────────────


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        Uuid, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True
    )
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(20), nullable=False)
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


# ── LLM Usage Events ───────────────────────────────────────────────


class LLMUsageEvent(Base):
    """One row per LLM API call. Used for cost attribution and budget enforcement."""

    __tablename__ = "llm_usage_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
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
    provider = Column(String(50), nullable=False)
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


# ── Attachments ─────────────────────────────────────────────────────


ALLOWED_ATTACHMENT_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024


class Attachment(Base):
    """Binary image blob stored in Postgres. Capped at 10 MB, image/* only."""

    __tablename__ = "attachments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
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
    """Junction: channel_message <-> attachment (multiple images per message)."""

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


# ── Project Documents ───────────────────────────────────────────────


class ProjectDocument(Base):
    """Architecture document. Writable by both users and the manager agent.

    Well-known doc_type values:
      'architecture_source_of_truth', 'arc42_lite', 'c4_diagrams', 'adr/<slug>'
    """

    __tablename__ = "project_documents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
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

    project = relationship("Project", back_populates="documents")
    updated_by_agent = relationship("Agent", foreign_keys=[updated_by_agent_id])
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id])
    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )

    __table_args__ = (
        Index("ix_project_documents_project", "project_id", "updated_at"),
    )


class DocumentVersion(Base):
    """Version snapshot of a project document. Created before every edit."""

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


# ── Knowledge Base (RAG) ────────────────────────────────────────────


KNOWLEDGE_VALID_FILE_TYPES = frozenset({"pdf", "txt", "markdown", "csv"})
KNOWLEDGE_VALID_STATUSES = frozenset({"pending", "indexing", "indexed", "failed"})


class KnowledgeDocument(Base):
    """Uploaded document in a project's RAG knowledge base."""

    __tablename__ = "knowledge_documents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id = Column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    mime_type = Column(String(100), nullable=False)
    original_size_bytes = Column(Integer, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    project = relationship("Project", back_populates="knowledge_documents")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])
    chunks = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_documents_project_created", "project_id", "created_at"),
        Index("ix_knowledge_documents_project_status", "project_id", "status"),
    )


class KnowledgeChunk(Base):
    """Chunked excerpt with 1024-dim embedding (Voyage-3-large) for cosine search."""

    __tablename__ = "knowledge_chunks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(
        Uuid, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    embedding = Column(_VECTOR_1024, nullable=True)
    metadata_ = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    document = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        Index("ix_knowledge_chunks_doc_idx", "document_id", "chunk_index", unique=True),
        Index("ix_knowledge_chunks_project", "project_id", "created_at"),
        # HNSW vector index created via raw DDL in migration (Alembic can't render it).
    )
