from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgentTaskQueueItem(BaseModel):
    id: UUID
    title: str
    status: str
    critical: int
    urgent: int
    module_path: str | None
    updated_at: datetime


class AgentResponse(BaseModel):
    id: UUID
    project_id: UUID
    template_id: UUID | None = None
    role: str
    display_name: str
    tier: str | None = None
    model: str
    provider: str | None = None
    thinking_enabled: bool = False
    status: str
    current_task_id: UUID | None
    sandbox_id: str | None
    sandbox_persist: bool
    memory: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusWithQueueResponse(AgentResponse):
    queue_size: int = 0
    pending_message_count: int = 0
    task_queue: list[AgentTaskQueueItem] = Field(default_factory=list)


class UpdateAgentRequest(BaseModel):
    """PATCH /agents/{id} — update model, provider, thinking_enabled, or token_allocations."""
    model: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, max_length=50)
    thinking_enabled: bool | None = None
    display_name: str | None = Field(None, min_length=1, max_length=100)
    # Per-agent token allocation overrides. None = do not change. Empty dict = reset to defaults.
    # Shape: {incoming_msg_tokens, memory_pct, past_session_pct, current_session_pct}
    token_allocations: dict | None = Field(None)


class SpawnEngineerCreate(BaseModel):
    """Request body for spawning a new engineer."""

    project_id: UUID
    display_name: str | None = None
    template_id: UUID | None = None
    seniority: str | None = None
    module_path: str | None = None


class AgentTool(BaseModel):
    """Tool available to an agent."""
    name: str
    description: str | None = None


class AgentContextResponse(BaseModel):
    """Agent context for the Inspector panel.

    Includes real assembled system prompt (from DB block configs), available tools,
    and recent message history.
    """
    id: UUID
    project_id: UUID
    template_id: UUID | None = None
    role: str
    display_name: str
    tier: str | None = None
    model: str
    provider: str | None = None
    thinking_enabled: bool = False
    status: str
    system_prompt: str | None = None
    available_tools: list[AgentTool] = Field(default_factory=list)
    recent_messages: list[dict] = Field(default_factory=list, description="Last N messages in agent context")
    sandbox_id: str | None = None
    sandbox_active: bool = False
