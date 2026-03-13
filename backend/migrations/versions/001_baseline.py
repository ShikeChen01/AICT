"""Baseline: full schema from models.py (v2 redesign).

Creates the entire schema in a single idempotent operation.
For existing databases, stamp this revision instead of running it:

    alembic stamp 001_baseline

Revision ID: 001_baseline
Revises: —
Create Date: 2026-03-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── pgvector extension ───────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("firebase_uid", sa.String(128), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("github_token", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── projects ─────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("spec_repo_path", sa.String(512), nullable=False),
        sa.Column("code_repo_url", sa.String(512), nullable=False),
        sa.Column("code_repo_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── sandbox_configs ──────────────────────────────────────────────
    op.create_table(
        "sandbox_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("os_image", sa.String(100), nullable=False, server_default="ubuntu-22.04"),
        sa.Column("setup_script", sa.Text(), nullable=False, server_default=""),
        sa.Column("persistent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_sandbox_configs_user_name"),
    )

    # ── project_memberships ──────────────────────────────────────────
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_memberships_project_user", "project_memberships", ["project_id", "user_id"], unique=True)
    op.create_index("ix_project_memberships_user", "project_memberships", ["user_id"])

    # ── project_settings ─────────────────────────────────────────────
    op.create_table(
        "project_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("max_engineers", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("persistent_sandbox_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model_overrides", sa.JSON(), nullable=True),
        sa.Column("prompt_overrides", sa.JSON(), nullable=True),
        sa.Column("daily_token_budget", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_per_hour_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_per_hour_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_cost_budget_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("knowledge_max_documents", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("knowledge_max_total_bytes", sa.BigInteger(), nullable=False, server_default=str(100 * 1024 * 1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── project_secrets ──────────────────────────────────────────────
    op.create_table(
        "project_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("hint", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_project_secrets_project_name"),
    )

    # ── agent_templates ──────────────────────────────────────────────
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_role", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tool_access", sa.JSON(), nullable=True),
        sa.Column("sandbox_template", sa.String(100), nullable=True),
        sa.Column("knowledge_sources", sa.JSON(), nullable=True),
        sa.Column("trigger_config", sa.JSON(), nullable=True),
        sa.Column("cost_limits", sa.JSON(), nullable=True),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_templates_project", "agent_templates", ["project_id"])

    # ── tasks (before agents — agents FK → tasks) ────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="backlog"),
        sa.Column("critical", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("urgent", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("assigned_agent_id", sa.Uuid(), nullable=True),
        sa.Column("module_path", sa.String(512), nullable=True),
        sa.Column("git_branch", sa.String(255), nullable=True),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column("parent_task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"])

    # ── agents ───────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="sleeping"),
        sa.Column("current_task_id", sa.Uuid(), sa.ForeignKey("tasks.id", use_alter=True, name="fk_agent_current_task"), nullable=True),
        sa.Column("memory", sa.JSON(), nullable=True),
        sa.Column("token_allocations", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_project_status", "agents", ["project_id", "status"])
    op.create_index("ix_agents_project_role", "agents", ["project_id", "role"])

    # Deferred FKs: tasks → agents
    op.create_foreign_key("fk_tasks_assigned_agent", "tasks", "agents", ["assigned_agent_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_tasks_created_by", "tasks", "agents", ["created_by_id"], ["id"], ondelete="SET NULL")

    # ── sandboxes (runtime instances) ────────────────────────────────
    op.create_table(
        "sandboxes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sandbox_config_id", sa.Uuid(), sa.ForeignKey("sandbox_configs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("orchestrator_sandbox_id", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="provisioning"),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("port", sa.Integer(), server_default="8080"),
        sa.Column("auth_token", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── sandbox_snapshots ────────────────────────────────────────────
    op.create_table(
        "sandbox_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sandbox_id", sa.Uuid(), sa.ForeignKey("sandboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("k8s_snapshot_name", sa.String(255), nullable=False),
        sa.Column("os_image", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── sandbox_usage_events ─────────────────────────────────────────
    op.create_table(
        "sandbox_usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sandbox_id", sa.Uuid(), sa.ForeignKey("sandboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("pod_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── mcp_server_configs ───────────────────────────────────────────
    op.create_table(
        "mcp_server_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.LargeBinary(), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(30), nullable=False, server_default="disconnected"),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_server_configs_agent", "mcp_server_configs", ["agent_id"])

    # ── prompt_block_configs ─────────────────────────────────────────
    op.create_table(
        "prompt_block_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("block_key", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prompt_block_configs_template", "prompt_block_configs", ["template_id", "position"])
    op.create_index("ix_prompt_block_configs_agent", "prompt_block_configs", ["agent_id", "position"])

    # ── tool_configs ─────────────────────────────────────────────────
    op.create_table(
        "tool_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("agent_templates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detailed_description", sa.Text(), nullable=True),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("allowed_roles", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="native"),
        sa.Column("mcp_server_id", sa.Uuid(), sa.ForeignKey("mcp_server_configs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_configs_agent", "tool_configs", ["agent_id", "position"])
    op.create_index("ix_tool_configs_template", "tool_configs", ["template_id", "position"])
    op.create_index("ix_tool_configs_mcp_server", "tool_configs", ["mcp_server_id"])

    # ── channel_messages ─────────────────────────────────────────────
    op.create_table(
        "channel_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("broadcast", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channel_target_status", "channel_messages", ["target_agent_id", "status", "created_at"])
    op.create_index("ix_channel_project", "channel_messages", ["project_id", "created_at"])

    # ── agent_sessions ───────────────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_message_id", sa.Uuid(), sa.ForeignKey("channel_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_sessions_agent", "agent_sessions", ["agent_id", "started_at"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])

    # ── agent_messages ───────────────────────────────────────────────
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_input", sa.JSON(), nullable=True),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("loop_iteration", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_messages_agent_time", "agent_messages", ["agent_id", "created_at"])
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id", "loop_iteration"])

    # ── llm_usage_events ─────────────────────────────────────────────
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_usage_project_time", "llm_usage_events", ["project_id", "created_at"])
    op.create_index("ix_llm_usage_agent", "llm_usage_events", ["agent_id"])
    op.create_index("ix_llm_usage_session", "llm_usage_events", ["session_id"])

    # ── attachments ──────────────────────────────────────────────────
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_attachments_project", "attachments", ["project_id", "created_at"])

    # ── message_attachments ──────────────────────────────────────────
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("channel_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), sa.ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_msg_attachments_message", "message_attachments", ["message_id"])
    op.create_index("ix_msg_attachments_attachment", "message_attachments", ["attachment_id"])

    # ── project_documents ────────────────────────────────────────────
    op.create_table(
        "project_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("updated_by_agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_documents_project", "project_documents", ["project_id", "updated_at"])

    # ── document_versions ────────────────────────────────────────────
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("project_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("edited_by_agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("edited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("edit_summary", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_versions_doc_num", "document_versions", ["document_id", "version_number"], unique=True)
    op.create_index("ix_document_versions_doc_time", "document_versions", ["document_id", "created_at"])

    # ── knowledge_documents ──────────────────────────────────────────
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_documents_project_created", "knowledge_documents", ["project_id", "created_at"])
    op.create_index("ix_knowledge_documents_project_status", "knowledge_documents", ["project_id", "status"])

    # ── knowledge_chunks (with pgvector) ─────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024)")
    op.create_index("ix_knowledge_chunks_doc_idx", "knowledge_chunks", ["document_id", "chunk_index"], unique=True)
    op.create_index("ix_knowledge_chunks_project", "knowledge_chunks", ["project_id", "created_at"])
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_assigned_agent", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_created_by", "tasks", type_="foreignkey")

    tables = [
        "knowledge_chunks",
        "knowledge_documents",
        "document_versions",
        "project_documents",
        "message_attachments",
        "attachments",
        "llm_usage_events",
        "agent_messages",
        "agent_sessions",
        "channel_messages",
        "tool_configs",
        "prompt_block_configs",
        "mcp_server_configs",
        "sandbox_usage_events",
        "sandbox_snapshots",
        "sandboxes",
        "agents",
        "tasks",
        "agent_templates",
        "project_secrets",
        "project_settings",
        "project_memberships",
        "sandbox_configs",
        "projects",
        "users",
    ]
    for table in tables:
        op.drop_table(table)

    op.execute("DROP EXTENSION IF EXISTS vector")
