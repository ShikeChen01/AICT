"""Agent Template CRUD endpoints.

Templates are reusable agent configurations (model, provider, thinking_enabled, prompt blocks).
System defaults (Manager, CTO, Engineer) are auto-created per project.
Users can create additional worker templates and edit all templates.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import AgentTemplate, User
from backend.db.repositories.agent_templates import AgentTemplateRepository
from backend.db.session import get_db
from backend.llm.model_resolver import infer_provider

router = APIRouter(prefix="/templates", tags=["templates"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class AgentTemplateResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    base_role: str
    model: str
    provider: str | None
    thinking_enabled: bool
    is_system_default: bool

    model_config = {"from_attributes": True}


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_role: str = Field(default="worker", pattern="^(worker)$")  # only worker for user-created
    model: str = Field(..., min_length=1, max_length=100)
    provider: str | None = Field(None, max_length=50)
    thinking_enabled: bool = Field(default=False)


class UpdateTemplateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, max_length=50)
    thinking_enabled: bool | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/templates", response_model=list[AgentTemplateResponse])
async def list_templates(
    project_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agent templates for a project."""
    if isinstance(current_user, User):
        await require_project_access(db, project_id, current_user.id)
    repo = AgentTemplateRepository(db)
    return await repo.list_by_project(project_id)


@router.post("/projects/{project_id}/templates", response_model=AgentTemplateResponse)
async def create_template(
    project_id: UUID,
    body: CreateTemplateRequest,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent template for a project (worker templates only)."""
    if isinstance(current_user, User):
        await require_project_access(db, project_id, current_user.id)
    repo = AgentTemplateRepository(db)
    template = await repo.create_with_blocks(
        project_id=project_id,
        name=body.name,
        base_role=body.base_role,
        model=body.model,
        provider=body.provider,
        thinking_enabled=body.thinking_enabled,
        is_system_default=False,
    )
    await db.commit()
    await db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=AgentTemplateResponse)
async def update_template(
    template_id: UUID,
    body: UpdateTemplateRequest,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a template. Changes only affect newly created agents."""
    result = await db.execute(select(AgentTemplate).where(AgentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if isinstance(current_user, User):
        await require_project_access(db, template.project_id, current_user.id)

    if body.name is not None:
        template.name = body.name
    if body.model is not None:
        template.model = body.model
        # If provider not explicitly set, re-infer from new model
        if body.provider is None:
            template.provider = infer_provider(body.model)
    if body.provider is not None:
        template.provider = body.provider
    if body.thinking_enabled is not None:
        template.thinking_enabled = body.thinking_enabled

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user-created template. System defaults cannot be deleted."""
    result = await db.execute(select(AgentTemplate).where(AgentTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if isinstance(current_user, User):
        await require_project_access(db, template.project_id, current_user.id)
    if template.is_system_default:
        raise HTTPException(status_code=400, detail="System default templates cannot be deleted.")

    await db.delete(template)
    await db.commit()
