import pytest

from backend.core.exceptions import InvalidAgentRole
from backend.services.orchestrator import OrchestratorService, sandbox_should_persist


def test_sandbox_policy_by_role():
    assert sandbox_should_persist("gm") is True
    assert sandbox_should_persist("om") is True
    assert sandbox_should_persist("engineer") is False


def test_sandbox_policy_invalid_role():
    with pytest.raises(InvalidAgentRole):
        sandbox_should_persist("invalid")


@pytest.mark.asyncio
async def test_orchestrator_creates_persistent_sandbox_for_gm(session, sample_gm):
    orchestrator = OrchestratorService()
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, sample_gm)
    assert sandbox.persistent is True
    assert sample_gm.sandbox_id is not None


@pytest.mark.asyncio
async def test_orchestrator_closes_ephemeral_engineer_sandbox(session, sample_engineer):
    orchestrator = OrchestratorService()
    sandbox = await orchestrator.ensure_sandbox_for_agent(session, sample_engineer)
    assert sandbox.persistent is False
    assert sample_engineer.sandbox_id is not None

    await orchestrator.close_if_ephemeral(session, sample_engineer)
    assert sample_engineer.sandbox_id is None

