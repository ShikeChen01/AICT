"""
Ticket service — handles ticket lifecycle including create, reply, close, and agent wake logic.

Ticket types: task_assignment, question, help, issue
- Higher priority agent (GM > OM > Engineer) closes tickets
- Tickets wake the target agent
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import (
    AgentNotFoundError,
    TicketCloseNotAllowed,
    TicketNotFoundError,
)
from backend.db.models import Agent, Ticket, TicketMessage, VALID_TICKET_TYPES, VALID_TICKET_STATUSES
from backend.schemas.ticket import TicketCreate, TicketMessageCreate, TicketResponse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TicketService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._ws_manager = None
        self._orchestrator = None

    @property
    def ws_manager(self):
        """Lazy load WebSocket manager to avoid circular imports."""
        if self._ws_manager is None:
            from backend.websocket.manager import ws_manager
            self._ws_manager = ws_manager
        return self._ws_manager

    @property
    def orchestrator(self):
        """Lazy load orchestrator to avoid circular imports."""
        if self._orchestrator is None:
            from backend.services.orchestrator import OrchestratorService
            self._orchestrator = OrchestratorService()
        return self._orchestrator

    async def get(self, ticket_id: UUID) -> Ticket:
        """Get a ticket by ID with messages loaded."""
        result = await self.session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.messages))
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def list_by_project(self, project_id: UUID, status: str | None = None) -> list[Ticket]:
        """List tickets for a project."""
        query = select(Ticket).where(Ticket.project_id == project_id)
        if status:
            query = query.where(Ticket.status == status)
        query = query.order_by(Ticket.critical, Ticket.urgent, Ticket.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_for_agent(self, agent_id: UUID, direction: str = "to") -> list[Ticket]:
        """
        List tickets for an agent.
        direction: 'to' (received) or 'from' (sent)
        """
        if direction == "to":
            query = select(Ticket).where(Ticket.to_agent_id == agent_id)
        else:
            query = select(Ticket).where(Ticket.from_agent_id == agent_id)

        query = query.order_by(Ticket.critical, Ticket.urgent, Ticket.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_open_for_agent(self, agent_id: UUID) -> list[Ticket]:
        """List open tickets where this agent is the recipient."""
        result = await self.session.execute(
            select(Ticket)
            .where(Ticket.to_agent_id == agent_id, Ticket.status == "open")
            .order_by(Ticket.critical, Ticket.urgent, Ticket.created_at)
        )
        return list(result.scalars().all())

    async def _get_agent(self, agent_id: UUID) -> Agent:
        """Helper to get an agent by ID."""
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise AgentNotFoundError(agent_id)
        return agent

    async def create(
        self,
        project_id: UUID,
        from_agent_id: UUID,
        data: TicketCreate,
    ) -> Ticket:
        """
        Create a new ticket and optionally an initial message.
        Wakes the target agent.
        """
        # Validate agents exist
        from_agent = await self._get_agent(from_agent_id)
        to_agent = await self._get_agent(data.to_agent_id)

        # Validate ticket type
        if data.ticket_type not in VALID_TICKET_TYPES:
            raise ValueError(f"Invalid ticket type: {data.ticket_type}")

        # Create ticket
        ticket = Ticket(
            project_id=project_id,
            from_agent_id=from_agent_id,
            to_agent_id=data.to_agent_id,
            header=data.header,
            ticket_type=data.ticket_type,
            critical=data.critical,
            urgent=data.urgent,
            status="open",
        )
        self.session.add(ticket)
        await self.session.flush()

        # Add initial message if provided
        if data.initial_message:
            message = TicketMessage(
                ticket_id=ticket.id,
                from_agent_id=from_agent_id,
                content=data.initial_message,
            )
            self.session.add(message)
            await self.session.flush()

        # Wake the target agent if sleeping
        await self._wake_agent(to_agent)

        await self.session.refresh(ticket)
        return ticket

    async def reply(
        self,
        ticket_id: UUID,
        from_agent_id: UUID,
        data: TicketMessageCreate,
    ) -> TicketMessage:
        """Add a reply to a ticket."""
        ticket = await self.get(ticket_id)

        # Validate the agent is part of the ticket
        if from_agent_id not in (ticket.from_agent_id, ticket.to_agent_id):
            raise TicketCloseNotAllowed("Agent is not part of this ticket")

        # Validate ticket is open
        if ticket.status != "open":
            raise ValueError("Cannot reply to a closed ticket")

        message = TicketMessage(
            ticket_id=ticket_id,
            from_agent_id=from_agent_id,
            content=data.content,
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)

        # Wake the other agent in the ticket
        other_agent_id = (
            ticket.to_agent_id if from_agent_id == ticket.from_agent_id
            else ticket.from_agent_id
        )
        other_agent = await self._get_agent(other_agent_id)
        await self._wake_agent(other_agent)

        return message

    async def close(self, ticket_id: UUID, closing_agent_id: UUID) -> Ticket:
        """
        Close a ticket.
        Only the higher-priority agent (GM > OM > Engineer) can close.
        """
        ticket = await self.get(ticket_id)

        if ticket.status == "closed":
            return ticket

        # Get both agents to check priority
        from_agent = await self._get_agent(ticket.from_agent_id)
        to_agent = await self._get_agent(ticket.to_agent_id)
        closing_agent = await self._get_agent(closing_agent_id)

        # Check if closing agent is part of the ticket
        if closing_agent_id not in (ticket.from_agent_id, ticket.to_agent_id):
            raise TicketCloseNotAllowed("Agent is not part of this ticket")

        # Determine the other agent
        other_agent = from_agent if closing_agent_id == ticket.to_agent_id else to_agent

        # Higher priority = lower priority number (GM=0, OM=1, Engineer=2)
        if closing_agent.priority > other_agent.priority:
            raise TicketCloseNotAllowed(
                f"Only the higher-priority agent ({other_agent.role}) can close this ticket"
            )

        ticket.status = "closed"
        ticket.closed_at = _utcnow()
        ticket.closed_by_id = closing_agent_id

        await self.session.flush()
        await self.session.refresh(ticket)

        return ticket

    async def _wake_agent(self, agent: Agent) -> None:
        """Wake an agent and ensure sandbox availability."""
        prev_status = agent.status
        prev_sandbox_id = agent.sandbox_id
        await self.orchestrator.wake_agent(self.session, agent)
        if agent.status != prev_status or agent.sandbox_id != prev_sandbox_id:
            await self.ws_manager.broadcast_agent_status(agent)


def get_ticket_service(session: AsyncSession) -> TicketService:
    """Factory function to create TicketService instance."""
    return TicketService(session)
