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
    role: str
    display_name: str
    model: str
    status: str
    current_task_id: UUID | None
    sandbox_id: str | None
    sandbox_persist: bool
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusWithQueueResponse(AgentResponse):
    queue_size: int = 0
    open_ticket_count: int = 0
    task_queue: list[AgentTaskQueueItem] = Field(default_factory=list)


class SpawnEngineerCreate(BaseModel):
    """Request body for spawning a new engineer."""

    project_id: UUID
    display_name: str | None = None
    model: str = "claude-4.5"
    module_path: str | None = None


class AgentTool(BaseModel):
    """Tool available to an agent."""
    name: str
    description: str | None = None


class AgentContextResponse(BaseModel):
    """
    Agent context for the Inspector panel (Frontend V2).
    
    Includes system prompt, available tools, and recent message history.
    """
    id: UUID
    role: str
    display_name: str
    model: str
    status: str
    system_prompt: str | None = None
    available_tools: list[AgentTool] = Field(default_factory=list)
    recent_messages: list[dict] = Field(default_factory=list, description="Last N messages in agent context")
    sandbox_id: str | None = None
    sandbox_active: bool = False
