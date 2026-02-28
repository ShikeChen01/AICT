"""Project document repository — manager-agent writes, user read-only."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProjectDocument
from backend.db.repositories.base import BaseRepository


class ProjectDocumentRepository(BaseRepository[ProjectDocument]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProjectDocument, session)

    async def list_by_project(self, project_id: UUID) -> list[ProjectDocument]:
        result = await self.session.execute(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_type(self, project_id: UUID, doc_type: str) -> ProjectDocument | None:
        result = await self.session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.doc_type == doc_type,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        project_id: UUID,
        doc_type: str,
        content: str,
        title: str | None,
        agent_id: UUID,
    ) -> ProjectDocument:
        """Insert or update a document. Uses PostgreSQL ON CONFLICT DO UPDATE."""
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(ProjectDocument)
            .values(
                project_id=project_id,
                doc_type=doc_type,
                content=content,
                title=title,
                updated_by_agent_id=agent_id,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_project_documents_project_type",
                set_={
                    "content": content,
                    "title": title,
                    "updated_by_agent_id": agent_id,
                    "updated_at": now,
                },
            )
            .returning(ProjectDocument)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()
