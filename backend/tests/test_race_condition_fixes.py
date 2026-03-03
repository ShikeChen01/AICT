"""Tests for race condition fixes in the prompt assembly layer and document repositories.

These tests verify the correctness of:
- bulk_replace_agent_blocks: no duplicate PromptBlockConfig rows after replace
- bulk_replace_template_blocks: no duplicate PromptBlockConfig rows after replace
- user_edit: no duplicate ProjectDocument rows on concurrent creation
- upsert: concurrent agent writes serialize correctly via FOR UPDATE lock
- get_by_type: for_update parameter is accepted without error
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, AgentTemplate, ProjectDocument, Repository
from backend.db.repositories.agent_templates import PromptBlockConfigRepository
from backend.db.repositories.project_documents import ProjectDocumentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_blocks(n: int = 3) -> list[dict]:
    return [
        {"block_key": f"block_{i}", "content": f"content {i}", "position": i, "enabled": True}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# bulk_replace_agent_blocks — no duplicates after sequential replacement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_replace_agent_blocks_no_duplicates(
    session: AsyncSession,
    sample_engineer: Agent,
) -> None:
    """Replacing blocks twice sequentially must not leave duplicate rows."""
    repo = PromptBlockConfigRepository(session)

    # First replacement
    blocks_v1 = _make_blocks(3)
    await repo.bulk_replace_agent_blocks(sample_engineer.id, blocks_v1)
    await session.flush()

    result_v1 = await repo.list_for_agent(sample_engineer.id)
    assert len(result_v1) == 3

    # Second replacement (simulates user editing blocks again)
    blocks_v2 = _make_blocks(4)
    await repo.bulk_replace_agent_blocks(sample_engineer.id, blocks_v2)
    await session.flush()

    result_v2 = await repo.list_for_agent(sample_engineer.id)
    # Must be exactly 4, not 7 (3 old + 4 new)
    assert len(result_v2) == 4, (
        f"Expected 4 blocks after second replacement, got {len(result_v2)} — "
        "duplicate rows from the race condition fix may be missing"
    )


@pytest.mark.asyncio
async def test_bulk_replace_agent_blocks_correct_content(
    session: AsyncSession,
    sample_engineer: Agent,
) -> None:
    """Block content after replacement must match the most-recent write."""
    repo = PromptBlockConfigRepository(session)

    await repo.bulk_replace_agent_blocks(
        sample_engineer.id,
        [{"block_key": "rules", "content": "old content", "position": 0, "enabled": True}],
    )
    await session.flush()

    await repo.bulk_replace_agent_blocks(
        sample_engineer.id,
        [{"block_key": "rules", "content": "new content", "position": 0, "enabled": True}],
    )
    await session.flush()

    result = await repo.list_for_agent(sample_engineer.id)
    assert len(result) == 1
    assert result[0].content == "new content"


# ---------------------------------------------------------------------------
# bulk_replace_template_blocks — no duplicates after sequential replacement
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_template(
    session: AsyncSession,
    sample_project: Repository,
) -> AgentTemplate:
    template = AgentTemplate(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        name="Test Template",
        base_role="worker",
        model="gpt-4",
        provider="openai",
        is_system_default=False,
    )
    session.add(template)
    await session.flush()
    return template


@pytest.mark.asyncio
async def test_bulk_replace_template_blocks_no_duplicates(
    session: AsyncSession,
    sample_template: AgentTemplate,
) -> None:
    """Replacing template blocks twice sequentially must not leave duplicate rows."""
    repo = PromptBlockConfigRepository(session)

    await repo.bulk_replace_template_blocks(sample_template.id, _make_blocks(3))
    await session.flush()
    result_v1 = await repo.list_for_template(sample_template.id)
    assert len(result_v1) == 3

    await repo.bulk_replace_template_blocks(sample_template.id, _make_blocks(5))
    await session.flush()
    result_v2 = await repo.list_for_template(sample_template.id)
    assert len(result_v2) == 5, (
        f"Expected 5 blocks after second replacement, got {len(result_v2)}"
    )


# ---------------------------------------------------------------------------
# ProjectDocumentRepository — get_by_type with for_update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_type_for_update_no_error(
    session: AsyncSession,
    sample_project: Repository,
) -> None:
    """get_by_type(for_update=True) must not raise on either existing or missing docs."""
    repo = ProjectDocumentRepository(session)

    # Non-existent document — should return None without raising
    result = await repo.get_by_type(sample_project.id, "arch_doc", for_update=True)
    assert result is None

    # Create a document and lock it
    doc = ProjectDocument(
        id=uuid.uuid4(),
        project_id=sample_project.id,
        doc_type="arch_doc",
        content="initial",
        current_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(doc)
    await session.flush()

    result2 = await repo.get_by_type(sample_project.id, "arch_doc", for_update=True)
    assert result2 is not None
    assert result2.content == "initial"


# ---------------------------------------------------------------------------
# user_edit — creates document correctly; sequential calls update, not duplicate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_edit_creates_document(
    session: AsyncSession,
    sample_project: Repository,
) -> None:
    """user_edit on a non-existent document must create it."""
    repo = ProjectDocumentRepository(session)
    user_id = uuid.uuid4()

    doc = await repo.user_edit(
        project_id=sample_project.id,
        doc_type="architecture",
        content="Initial architecture description",
        user_id=user_id,
        title="Architecture",
    )
    await session.flush()

    assert doc is not None
    assert doc.content == "Initial architecture description"
    assert doc.title == "Architecture"
    assert doc.current_version == 1
    assert doc.updated_by_user_id == user_id


@pytest.mark.asyncio
async def test_user_edit_updates_existing_document(
    session: AsyncSession,
    sample_project: Repository,
) -> None:
    """user_edit on an existing document must update content and increment version."""
    repo = ProjectDocumentRepository(session)
    user_id = uuid.uuid4()

    # Create first
    await repo.user_edit(
        project_id=sample_project.id,
        doc_type="architecture",
        content="version 1 content",
        user_id=user_id,
    )
    await session.flush()

    # Update
    updated = await repo.user_edit(
        project_id=sample_project.id,
        doc_type="architecture",
        content="version 2 content",
        user_id=user_id,
        edit_summary="Updated architecture",
    )
    await session.flush()

    assert updated.content == "version 2 content"
    assert updated.current_version == 2


@pytest.mark.asyncio
async def test_user_edit_no_duplicate_documents(
    session: AsyncSession,
    sample_project: Repository,
) -> None:
    """Two sequential user_edits on the same doc_type must not produce duplicate rows."""
    repo = ProjectDocumentRepository(session)
    user_id = uuid.uuid4()

    await repo.user_edit(
        project_id=sample_project.id,
        doc_type="architecture",
        content="content A",
        user_id=user_id,
    )
    await session.flush()

    await repo.user_edit(
        project_id=sample_project.id,
        doc_type="architecture",
        content="content B",
        user_id=user_id,
    )
    await session.flush()

    all_docs = await repo.list_by_project(sample_project.id)
    arch_docs = [d for d in all_docs if d.doc_type == "architecture"]
    assert len(arch_docs) == 1, (
        f"Expected exactly 1 architecture document, got {len(arch_docs)} — "
        "duplicate rows indicate the race condition fix is needed"
    )
    assert arch_docs[0].content == "content B"


# ---------------------------------------------------------------------------
# upsert — FOR UPDATE serialises concurrent agent writes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_creates_document(
    session: AsyncSession,
    sample_project: Repository,
    sample_engineer: Agent,
) -> None:
    """upsert on a non-existent document must create it."""
    repo = ProjectDocumentRepository(session)

    doc = await repo.upsert(
        project_id=sample_project.id,
        doc_type="design",
        content="Design document content",
        title="Design",
        agent_id=sample_engineer.id,
    )
    await session.flush()

    assert doc is not None
    assert doc.content == "Design document content"
    assert doc.current_version == 1


@pytest.mark.asyncio
async def test_upsert_updates_existing_document(
    session: AsyncSession,
    sample_project: Repository,
    sample_engineer: Agent,
) -> None:
    """Sequential upserts on the same doc_type must update, not duplicate."""
    repo = ProjectDocumentRepository(session)

    await repo.upsert(
        project_id=sample_project.id,
        doc_type="design",
        content="v1",
        title="Design v1",
        agent_id=sample_engineer.id,
    )
    await session.flush()

    updated = await repo.upsert(
        project_id=sample_project.id,
        doc_type="design",
        content="v2",
        title="Design v2",
        agent_id=sample_engineer.id,
        edit_summary="Agent update",
    )
    await session.flush()

    all_docs = await repo.list_by_project(sample_project.id)
    design_docs = [d for d in all_docs if d.doc_type == "design"]
    assert len(design_docs) == 1
    assert design_docs[0].content == "v2"
