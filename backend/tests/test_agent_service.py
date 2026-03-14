"""
Tests for AgentService.

v3.1: Removed role-based tests (count_by_role, MaxEngineersReached limits,
sandbox_should_persist assertions). Agent creation is now template-driven
and role-agnostic. Legacy methods are preserved for backward compat but
no longer enforce role-based constraints.
"""

import uuid

import pytest

from backend.core.exceptions import ProjectNotFoundError
from backend.services.agent_service import get_agent_service


@pytest.mark.asyncio
async def test_spawn_engineer(session, sample_project):
    """spawn_engineer is DEPRECATED but still functional."""
    service = get_agent_service(session)
    agent = await service.spawn_engineer(sample_project.id)
    assert agent.role == "engineer"
    assert agent.display_name == "Engineer-1"
    assert agent.status == "sleeping"


@pytest.mark.asyncio
async def test_spawn_engineer_with_display_name(session, sample_project):
    service = get_agent_service(session)
    agent = await service.spawn_engineer(
        sample_project.id,
        display_name="Backend-Engineer",
    )
    assert agent.display_name == "Backend-Engineer"


@pytest.mark.asyncio
async def test_spawn_engineer_no_max_limit(session, sample_project):
    """v3.1: No engineer cap — users manage their own agent fleet."""
    service = get_agent_service(session)
    agents = []
    for i in range(8):
        a = await service.spawn_engineer(sample_project.id)
        agents.append(a)
    assert len(agents) == 8


@pytest.mark.asyncio
async def test_ensure_project_agents_creates_manager_cto(session, sample_project):
    """ensure_project_agents is DEPRECATED but still creates manager + CTO."""
    service = get_agent_service(session)
    manager, cto = await service.ensure_project_agents(sample_project)
    assert manager.role == "manager"
    assert manager.display_name == "GM"
    assert cto.role == "cto"
    assert cto.display_name == "CTO"


@pytest.mark.asyncio
async def test_ensure_project_agents_idempotent(session, sample_project, sample_gm, sample_om):
    service = get_agent_service(session)
    manager, cto = await service.ensure_project_agents(sample_project)
    assert manager.id == sample_gm.id
    assert cto.id == sample_om.id


@pytest.mark.asyncio
async def test_get_or_create_project_agents_raises_if_project_missing(session, sample_project):
    service = get_agent_service(session)
    fake_id = uuid.uuid4()
    with pytest.raises(ProjectNotFoundError):
        await service.get_or_create_project_agents(fake_id)


@pytest.mark.asyncio
async def test_get_or_create_project_agents_creates_if_missing(session, sample_project):
    service = get_agent_service(session)
    manager, cto = await service.get_or_create_project_agents(sample_project.id)
    assert manager.project_id == sample_project.id
    assert cto.project_id == sample_project.id
