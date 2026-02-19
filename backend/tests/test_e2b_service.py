"""Unit tests for E2BService sandbox recovery behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.e2b_service import E2BService, SandboxMetadata


@pytest.mark.asyncio
async def test_ensure_running_sandbox_creates_when_missing(sample_engineer, session) -> None:
    sample_engineer.sandbox_id = None
    svc = E2BService()
    expected = SandboxMetadata(
        sandbox_id="sandbox-new",
        agent_id=str(sample_engineer.id),
        persistent=False,
        status="running",
        created=True,
        message="Sandbox created: sandbox-new",
    )

    with patch.object(E2BService, "create_sandbox", AsyncMock(return_value=expected)) as create_mock:
        result = await svc.ensure_running_sandbox(session, sample_engineer, persistent=False)

    assert result.created is True
    assert result.sandbox_id == "sandbox-new"
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_running_sandbox_recreates_when_not_found(sample_engineer, session) -> None:
    sample_engineer.sandbox_id = "sandbox-old"
    sample_engineer.sandbox_persist = False
    svc = E2BService()

    async def _fake_create(_session, agent, persistent):
        agent.sandbox_id = "sandbox-new"
        return SandboxMetadata(
            sandbox_id="sandbox-new",
            agent_id=str(agent.id),
            persistent=persistent,
            status="running",
            created=True,
        )

    with patch.object(E2BService, "_should_use_real_provider", return_value=True):
        with patch.object(E2BService, "_apply_sdk_api_key", return_value=None):
            with patch("backend.services.e2b_service.AsyncSandbox") as mock_async_sandbox:
                mock_async_sandbox.connect = AsyncMock(
                    side_effect=RuntimeError("Paused sandbox sandbox-old not found")
                )
                with patch.object(E2BService, "create_sandbox", side_effect=_fake_create) as create_mock:
                    result = await svc.ensure_running_sandbox(session, sample_engineer, persistent=False)

    assert result.restarted is True
    assert result.previous_sandbox_id == "sandbox-old"
    assert result.sandbox_id == "sandbox-new"
    assert "Sandbox restarted" in result.message
    assert create_mock.await_count == 1
