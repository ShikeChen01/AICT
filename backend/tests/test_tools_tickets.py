"""
Unit tests for ticket tools (request_human_input, report_to_manager, abort_mission).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Task, Ticket
from backend.tools.tickets import report_to_manager, abort_mission


class _SessionContext:
    """Async context manager that yields the test session."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


class TestReportToManager:
    """Tests for report_to_manager tool."""

    @pytest.mark.asyncio
    async def test_report_creates_ticket_and_returns_message(
        self,
        session: AsyncSession,
        sample_project,
        sample_manager,
        sample_engineer,
    ):
        """report_to_manager creates a ticket and returns success message."""
        await session.commit()
        with patch(
            "backend.tools.tickets.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            mock_ws = MagicMock()
            mock_ws.broadcast_ticket_created = AsyncMock(return_value=1)
            mock_ws.broadcast_agent_status = AsyncMock(return_value=1)
            with patch("backend.websocket.manager.ws_manager", mock_ws):
                result = await report_to_manager.ainvoke(
                    {
                        "agent_id": str(sample_engineer.id),
                        "project_id": str(sample_project.id),
                        "header": "Status update",
                        "message": "Step 1 done",
                        "ticket_type": "help",
                    }
                )
        assert "Report sent" in result
        assert "Status update" in result

        # Ticket was created in DB
        from sqlalchemy import select
        from backend.db.models import Ticket as TicketModel
        r = await session.execute(select(TicketModel).where(TicketModel.header == "Status update"))
        ticket = r.scalar_one_or_none()
        assert ticket is not None
        assert ticket.ticket_type == "help"


class TestAbortMission:
    """Tests for abort_mission tool."""

    @pytest.mark.asyncio
    async def test_abort_updates_task_and_agent(
        self,
        session: AsyncSession,
        sample_project,
        sample_engineer,
        sample_task,
    ):
        """abort_mission sets task to aborted and clears agent current_task_id."""
        sample_task.status = "in_progress"
        sample_task.assigned_agent_id = sample_engineer.id
        sample_engineer.current_task_id = sample_task.id
        sample_engineer.status = "busy"
        await session.commit()

        with patch(
            "backend.tools.tickets.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            with patch(
                "backend.websocket.manager.ws_manager",
                broadcast_mission_aborted=AsyncMock(return_value=1),
            ):
                result = await abort_mission.ainvoke(
                {
                    "agent_id": str(sample_engineer.id),
                    "task_id": str(sample_task.id),
                    "reason": "Blocked by missing API key",
                    "documentation": "Tried env var and config; key not found.",
                }
                )

        assert "ABORTED" in result
        assert "Blocked by missing API key" in result

        await session.refresh(sample_task)
        await session.refresh(sample_engineer)
        assert sample_task.status == "aborted"
        assert sample_task.abort_reason == "Blocked by missing API key"
        assert sample_task.abort_documentation == "Tried env var and config; key not found."
        assert sample_task.aborted_by_id == sample_engineer.id
        assert sample_engineer.current_task_id is None
        assert sample_engineer.status == "active"

    @pytest.mark.asyncio
    async def test_abort_task_not_found(self, session: AsyncSession, sample_engineer):
        """abort_mission returns error when task does not exist."""
        await session.commit()
        bad_task_id = str(uuid.uuid4())
        with patch(
            "backend.tools.tickets.AsyncSessionLocal",
            return_value=_SessionContext(session),
        ):
            result = await abort_mission.ainvoke(
            {
                "agent_id": str(sample_engineer.id),
                "task_id": bad_task_id,
                "reason": "Reason",
                "documentation": "Docs",
            }
            )
        assert "not found" in result.lower()
