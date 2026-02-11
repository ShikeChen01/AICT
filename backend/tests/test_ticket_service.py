"""
Tests for ticket service.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import (
    AgentNotFoundError,
    TicketCloseNotAllowed,
    TicketNotFoundError,
)
from backend.db.models import Agent, Project
from backend.schemas.ticket import TicketCreate, TicketMessageCreate
from backend.services.ticket_service import TicketService


class TestTicketService:
    """Test ticket service methods."""

    @pytest.fixture
    def service(self, session: AsyncSession):
        return TicketService(session)

    async def test_create_ticket(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Test Ticket",
            ticket_type="question",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, data)

        assert ticket.header == "Test Ticket"
        assert ticket.ticket_type == "question"
        assert ticket.from_agent_id == sample_gm.id
        assert ticket.to_agent_id == sample_om.id
        assert ticket.status == "open"

    async def test_create_ticket_with_message(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
        session: AsyncSession,
    ):
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Ticket with message",
            ticket_type="help",
            initial_message="This is the initial message",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, data)

        # Reload to get messages
        ticket = await service.get(ticket.id)
        assert len(ticket.messages) == 1
        assert ticket.messages[0].content == "This is the initial message"

    async def test_create_ticket_invalid_type(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Bad Type",
            ticket_type="invalid_type",
        )
        with pytest.raises(ValueError):
            await service.create(sample_project.id, sample_gm.id, data)

    async def test_create_ticket_invalid_agent(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
    ):
        data = TicketCreate(
            to_agent_id=uuid.uuid4(),
            header="Bad Agent",
            ticket_type="question",
        )
        with pytest.raises(AgentNotFoundError):
            await service.create(sample_project.id, sample_gm.id, data)

    async def test_get_ticket(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Get Test",
            ticket_type="issue",
        )
        created = await service.create(sample_project.id, sample_gm.id, data)

        ticket = await service.get(created.id)
        assert ticket.id == created.id

    async def test_get_ticket_not_found(self, service: TicketService):
        with pytest.raises(TicketNotFoundError):
            await service.get(uuid.uuid4())

    async def test_reply_to_ticket(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        # Create ticket
        create_data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Reply Test",
            ticket_type="question",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, create_data)

        # Reply from OM
        reply_data = TicketMessageCreate(content="This is a reply")
        message = await service.reply(ticket.id, sample_om.id, reply_data)

        assert message.content == "This is a reply"
        assert message.from_agent_id == sample_om.id

    async def test_reply_ticket_not_participant(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
        sample_engineer: Agent,
    ):
        # Create ticket between GM and OM
        create_data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Not Participant Test",
            ticket_type="question",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, create_data)

        # Try to reply from engineer (not a participant)
        reply_data = TicketMessageCreate(content="Should fail")
        with pytest.raises(TicketCloseNotAllowed):
            await service.reply(ticket.id, sample_engineer.id, reply_data)

    async def test_close_by_higher_priority(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        # Create ticket from OM to GM
        create_data = TicketCreate(
            to_agent_id=sample_gm.id,
            header="Close Test",
            ticket_type="question",
        )
        ticket = await service.create(sample_project.id, sample_om.id, create_data)

        # Close by GM (higher priority)
        closed = await service.close(ticket.id, sample_gm.id)
        assert closed.status == "closed"
        assert closed.closed_by_id == sample_gm.id
        assert closed.closed_at is not None

    async def test_close_by_lower_priority_fails(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_engineer: Agent,
    ):
        # Create ticket from GM to engineer
        create_data = TicketCreate(
            to_agent_id=sample_engineer.id,
            header="Close Fail Test",
            ticket_type="task_assignment",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, create_data)

        # Engineer (lower priority) tries to close
        with pytest.raises(TicketCloseNotAllowed):
            await service.close(ticket.id, sample_engineer.id)

    async def test_list_by_project(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        # Create tickets
        for i in range(3):
            data = TicketCreate(
                to_agent_id=sample_om.id,
                header=f"Ticket {i}",
                ticket_type="question",
            )
            await service.create(sample_project.id, sample_gm.id, data)

        tickets = await service.list_by_project(sample_project.id)
        assert len(tickets) >= 3

    async def test_list_open_for_agent(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
    ):
        # Create open ticket
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Open Ticket",
            ticket_type="question",
        )
        ticket = await service.create(sample_project.id, sample_gm.id, data)

        open_tickets = await service.list_open_for_agent(sample_om.id)
        assert any(t.id == ticket.id for t in open_tickets)

    async def test_wake_agent_on_ticket_create(
        self,
        service: TicketService,
        sample_project: Project,
        sample_gm: Agent,
        sample_om: Agent,
        session: AsyncSession,
    ):
        # Ensure OM is sleeping
        sample_om.status = "sleeping"
        await session.flush()

        # Create ticket to OM
        data = TicketCreate(
            to_agent_id=sample_om.id,
            header="Wake Test",
            ticket_type="question",
        )
        await service.create(sample_project.id, sample_gm.id, data)

        # OM should be woken
        await session.refresh(sample_om)
        assert sample_om.status == "active"
