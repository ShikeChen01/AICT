from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.orchestrator import OrchestratorService


@pytest.mark.asyncio
async def test_wake_agent_notifies_message_router(session, sample_manager, monkeypatch) -> None:
    orchestrator = OrchestratorService()
    router = MagicMock()
    expected_metadata = object()

    monkeypatch.setattr(
        "backend.workers.message_router.get_message_router",
        lambda: router,
    )
    monkeypatch.setattr(
        orchestrator,
        "ensure_sandbox_for_agent",
        AsyncMock(return_value=expected_metadata),
    )

    result = await orchestrator.wake_agent(session, sample_manager)

    assert result is expected_metadata
    router.notify.assert_called_once_with(sample_manager.id)
