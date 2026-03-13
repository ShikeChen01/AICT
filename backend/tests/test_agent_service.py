"""
Tests for AgentService.
"""

import pytest

from backend.config import settings
from backend.core.exceptions import MaxEngineersReached, ProjectNotFoundError
from backend.services.agent_service import get_agent_service


@pytest.mark.asyncio
async def test_count_by_role_empty(session, sample_project):
    service = get_agent_service(session)
    assert await service.count_by_role(sample_project.id, "engineer") == 0
    assert await service.count_by_role(sample_project.id, "manager") == 0


@pytest.mark.asyncio
async def test_count_by_role_after_spawn(session, sample_project, sample_engineer):
    service = get_agent_service(session)
    assert await service.count_by_role(sample_project.id, "engineer") == 1
    assert await service.count_by_role(sample_project.id, "manager") == 0


@pytest.mark.asyncio
async def test_spawn_engineer(session, sample_project):
    from backend.services.orchestrator import sandbox_should_persist
    service = get_agent_service(session)
    agent = await service.spawn_engineer(sample_project.id)
    assert agent.role == "engineer"
    assert agent.display_name == "Engineer-1"
    assert sandbox_should_persist(agent.role) is False
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
async def test_spawn_engineer_resolves_seniority_model(session, sample_project, monkeypatch):
    service = get_agent_service(session)
    monkeypatch.setattr(settings, "engineer_senior_model", "claude-4-6-sonnet-latest")
    agent = await service.spawn_engineer(
        sample_project.id,
        display_name="Engineer-Senior",
        seniority=" Senior ",
    )
    assert agent.model == "claude-4-6-sonnet-latest"


@pytest.mark.asyncio
async def test_spawn_engineer_invalid_seniority_defaults_to_junior(session, sample_project, monkeypatch):
    service = get_agent_service(session)
    monkeypatch.setattr(settings, "engineer_junior_model", "gemini-2.0-flash-lite")
    agent = await service.spawn_engineer(
        sample_project.id,
        display_name="Engineer-Junior-Defaulted",
        seniority="staff-plus",
    )
    assert agent.model == "gemini-2.0-flash-lite"


@pytest.mark.asyncio
async def test_spawn_engineer_max_limit(session, sample_project):
    service = get_agent_service(session)
    for i in range(5):
        await service.spawn_engineer(sample_project.id)
    with pytest.raises(MaxEngineersReached) as exc_info:
        await service.spawn_engineer(sample_project.id)
    assert "5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ensure_project_agents_creates_manager_cto(session, sample_project):
    from backend.services.orchestrator import sandbox_should_persist
    service = get_agent_service(session)
    manager, cto = await service.ensure_project_agents(sample_project)
    assert manager.role == "manager"
    assert manager.display_name == "GM"
    assert sandbox_should_persist(manager.role) is True
    assert cto.role == "cto"
    assert cto.display_name == "CTO"
    assert sandbox_should_persist(cto.role) is True


@pytest.mark.asyncio
async def test_ensure_project_agents_idempotent(session, sample_project, sample_gm, sample_om):
    service = get_agent_service(session)
    manager, cto = await service.ensure_project_agents(sample_project)
    assert manager.id == sample_gm.id
    assert cto.id == sample_om.id


@pytest.mark.asyncio
async def test_get_or_create_project_agents_raises_if_project_missing(session, sample_project):
    import uuid
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
