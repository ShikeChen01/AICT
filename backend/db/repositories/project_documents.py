"""Project document repository — user and agent writable, with version history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DocumentVersion, ProjectDocument
from backend.db.repositories.base import BaseRepository

_MAX_VERSIONS = 20


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

    async def get_by_type(self, project_id: UUID, doc_type: str, *, for_update: bool = False) -> ProjectDocument | None:
        q = (
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.doc_type == doc_type,
            )
        )
        if for_update:
            q = q.with_for_update()
        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def _snapshot_version(
        self,
        doc: ProjectDocument,
        *,
        edited_by_agent_id: UUID | None = None,
        edited_by_user_id: UUID | None = None,
        edit_summary: str | None = None,
    ) -> DocumentVersion | None:
        """Snapshot the current document content as a new version row.

        Prunes versions beyond _MAX_VERSIONS. Returns the new version or None
        if the document has no content yet.
        """
        if doc.content is None:
            return None

        new_version_number = (doc.current_version or 0) + 1

        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_number=new_version_number,
            content=doc.content,
            title=doc.title,
            edited_by_agent_id=edited_by_agent_id,
            edited_by_user_id=edited_by_user_id,
            edit_summary=edit_summary,
        )
        self.session.add(version)
        await self.session.flush()

        # Prune oldest versions beyond the cap
        all_versions = await self.session.execute(
            select(DocumentVersion.id, DocumentVersion.version_number)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
        )
        rows = all_versions.fetchall()
        if len(rows) > _MAX_VERSIONS:
            ids_to_delete = [r[0] for r in rows[_MAX_VERSIONS:]]
            await self.session.execute(
                delete(DocumentVersion).where(DocumentVersion.id.in_(ids_to_delete))
            )

        return version

    async def upsert(
        self,
        project_id: UUID,
        doc_type: str,
        content: str,
        title: str | None,
        agent_id: UUID,
        edit_summary: str | None = None,
    ) -> ProjectDocument:
        """Insert or update a document (agent write). Snapshots previous version."""
        now = datetime.now(timezone.utc)

        # Get or create the document; lock the row if it exists to prevent concurrent
        # version-number collisions during the snapshot + increment sequence.
        existing = await self.get_by_type(project_id, doc_type, for_update=True)
        if existing:
            # Snapshot current content before overwriting
            await self._snapshot_version(
                existing,
                edited_by_agent_id=agent_id,
                edit_summary=edit_summary or "Agent update",
            )
            existing.content = content
            existing.title = title
            existing.updated_by_agent_id = agent_id
            existing.updated_by_user_id = None
            existing.current_version = (existing.current_version or 0) + 1
            existing.updated_at = now
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        else:
            stmt = (
                pg_insert(ProjectDocument)
                .values(
                    project_id=project_id,
                    doc_type=doc_type,
                    content=content,
                    title=title,
                    updated_by_agent_id=agent_id,
                    updated_by_user_id=None,
                    current_version=1,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_project_documents_project_type",
                    set_={
                        "content": content,
                        "title": title,
                        "updated_by_agent_id": agent_id,
                        "updated_by_user_id": None,
                        "updated_at": now,
                    },
                )
                .returning(ProjectDocument)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.scalar_one()

    async def user_edit(
        self,
        project_id: UUID,
        doc_type: str,
        content: str,
        user_id: UUID,
        title: str | None = None,
        edit_summary: str | None = None,
    ) -> ProjectDocument:
        """User edits a document. Creates or updates with version snapshot."""
        now = datetime.now(timezone.utc)
        # Lock the row (if it exists) to serialise concurrent edits and prevent
        # version-number collisions in _snapshot_version.
        existing = await self.get_by_type(project_id, doc_type, for_update=True)

        if existing:
            # Snapshot current content before overwriting
            await self._snapshot_version(
                existing,
                edited_by_user_id=user_id,
                edit_summary=edit_summary or "User edit",
            )
            existing.content = content
            if title is not None:
                existing.title = title
            existing.updated_by_user_id = user_id
            existing.updated_by_agent_id = None
            existing.current_version = (existing.current_version or 0) + 1
            existing.updated_at = now
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        else:
            # Use INSERT ... ON CONFLICT DO UPDATE so that a concurrent insert
            # (another request that also saw no document and races to create one)
            # results in an update instead of a duplicate-entry error.
            stmt = (
                pg_insert(ProjectDocument)
                .values(
                    project_id=project_id,
                    doc_type=doc_type,
                    content=content,
                    title=title,
                    updated_by_user_id=user_id,
                    updated_by_agent_id=None,
                    current_version=1,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_project_documents_project_type",
                    set_={
                        "content": content,
                        "title": title,
                        "updated_by_user_id": user_id,
                        "updated_by_agent_id": None,
                        "updated_at": now,
                        # Treat the conflict as an update: increment version so the
                        # document version counter is never stuck at 1 after a race.
                        "current_version": ProjectDocument.__table__.c.current_version + 1,
                    },
                )
                .returning(ProjectDocument)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.scalar_one()

    async def list_versions(
        self, project_id: UUID, doc_type: str
    ) -> list[DocumentVersion]:
        """Return version history for a document (newest first)."""
        doc = await self.get_by_type(project_id, doc_type)
        if not doc:
            return []
        result = await self.session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, project_id: UUID, doc_type: str, version_number: int
    ) -> DocumentVersion | None:
        """Return a specific version of a document."""
        doc = await self.get_by_type(project_id, doc_type)
        if not doc:
            return None
        result = await self.session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def revert_to_version(
        self,
        project_id: UUID,
        doc_type: str,
        version_number: int,
        user_id: UUID,
    ) -> ProjectDocument | None:
        """Revert document to a past version (creates a new version, non-destructive)."""
        target_version = await self.get_version(project_id, doc_type, version_number)
        if not target_version:
            return None

        return await self.user_edit(
            project_id=project_id,
            doc_type=doc_type,
            content=target_version.content or "",
            user_id=user_id,
            title=target_version.title,
            edit_summary=f"Reverted to version {version_number}",
        )
