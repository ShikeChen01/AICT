"""
Chat service — handles user-GM conversation.

Features:
- Save user messages
- Invoke GM for response (non-streaming for MVP-0)
- Persist GM response
- WebSocket broadcast for real-time updates
"""

import logging
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.exceptions import AgentNotFoundError, ProjectNotFoundError
from backend.db.models import Agent, ChatMessage, Project
from backend.schemas.chat import ChatMessageCreate, ChatMessageResponse
from backend.services.orchestrator import OrchestratorService

logger = logging.getLogger(__name__)


class ChatService:
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
    def orchestrator(self) -> OrchestratorService:
        if self._orchestrator is None:
            self._orchestrator = OrchestratorService()
        return self._orchestrator

    async def _get_project(self, project_id: UUID) -> Project:
        """Get project by ID."""
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ProjectNotFoundError(project_id)
        return project

    async def _get_manager(self, project_id: UUID) -> Agent:
        """
        Get the Manager agent for a project.

        Supports both 'gm' and 'manager' roles (plan 3b1904f3 merges GM+OM into Manager).
        Prefers manager, falls back to gm for backward compatibility.
        """
        result = await self.session.execute(
            select(Agent)
            .where(
                Agent.project_id == project_id,
                Agent.role.in_(("manager", "gm")),
            )
            .order_by(case((Agent.role == "manager", 0), else_=1), Agent.priority)
            .limit(1)
        )
        manager = result.scalar_one_or_none()
        if not manager:
            raise AgentNotFoundError("Manager/GM not found for project")
        return manager

    async def get_history(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """Get chat history for a project."""
        await self._get_project(project_id)  # Validate project exists

        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.project_id == project_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        # Return in chronological order
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def send_message(
        self,
        project_id: UUID,
        data: ChatMessageCreate,
    ) -> tuple[ChatMessage, ChatMessage]:
        """
        Send a user message and get GM response.

        Returns tuple of (user_message, gm_response).

        For MVP-0, this is non-streaming - waits for full response.
        """
        await self._get_project(project_id)
        manager = await self._get_manager(project_id)

        # Save user message
        user_message = ChatMessage(
            project_id=project_id,
            role="user",
            content=data.content,
            attachments=data.attachments,
        )
        self.session.add(user_message)
        await self.session.flush()
        await self.session.refresh(user_message)

        # Broadcast user message
        await self.ws_manager.broadcast_chat_message(user_message)

        # Set Manager status to busy
        manager.status = "busy"
        await self.session.flush()
        await self.ws_manager.broadcast_gm_status(project_id, "busy")

        try:
            # Get chat history for context
            history = await self.get_history(project_id, limit=50)

            # Invoke Manager Graph (LangGraph)
            manager_response_content = await self._invoke_manager(manager, history, data.content)

            # Save Manager response (role 'gm' for backward compatibility with frontend)
            gm_message = ChatMessage(
                project_id=project_id,
                role="gm",
                content=manager_response_content,
            )
            self.session.add(gm_message)
            await self.session.flush()
            await self.session.refresh(gm_message)

            # Broadcast GM response
            await self.ws_manager.broadcast_chat_message(gm_message)

            return user_message, gm_message

        finally:
            # Set Manager status back to available
            manager.status = "active"
            await self.session.flush()
            await self.ws_manager.broadcast_gm_status(project_id, "available")

    async def _invoke_manager(
        self,
        manager: Agent,
        history: list[ChatMessage],
        user_message: str,
    ) -> str:
        """
        Invoke the Manager agent via LangGraph.
        """
        try:
            return await self.orchestrator.invoke_gm(
                session=self.session,
                gm=manager,
                history=history,
                user_message=user_message,
            )
        except Exception as exc:
            if not settings.llm_fallback_enabled:
                raise
            logger.exception("GM invocation failed, using fallback response: %s", exc)
            return (
                "[GM Fallback Response]\n\n"
                "I could not reach the configured model provider for this turn.\n"
                "Reason: provider unavailable.\n\n"
                f"I received your message: \"{user_message}\".\n"
                "Please retry shortly, or verify model API credentials/connectivity."
            )

    async def get_message(self, message_id: UUID) -> ChatMessage:
        """Get a single message by ID."""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            raise ValueError(f"Message {message_id} not found")
        return message


def get_chat_service(session: AsyncSession) -> ChatService:
    """Factory function to create ChatService instance."""
    return ChatService(session)
