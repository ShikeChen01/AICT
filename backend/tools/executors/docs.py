"""Tool executors — architecture document store (manager-only write)."""

from __future__ import annotations

from backend.db.repositories.project_documents import ProjectDocumentRepository
from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError

_VALID_DOC_TYPES = frozenset({
    "architecture_source_of_truth",
    "arc42_lite",
    "c4_diagrams",
})

_DOC_TYPE_HELP = (
    "Well-known values: 'architecture_source_of_truth', 'arc42_lite', 'c4_diagrams', "
    "or 'adr/<slug>' for individual ADRs (e.g. 'adr/001-use-postgresql')."
)


async def run_write_architecture_doc(ctx: RunContext, tool_input: dict) -> str:
    if ctx.agent.role != "manager":
        raise ToolExecutionError(
            message="write_architecture_doc is only available to the manager agent.",
            error_code="PERMISSION_DENIED",
            hint="Only the manager agent can update architecture documents.",
        )

    doc_type: str = tool_input.get("doc_type", "").strip()
    content: str = tool_input.get("content", "")
    title: str | None = tool_input.get("title") or None

    if not doc_type:
        raise ToolExecutionError(
            message="doc_type is required.",
            error_code="INVALID_INPUT",
            hint=_DOC_TYPE_HELP,
        )

    if doc_type not in _VALID_DOC_TYPES and not doc_type.startswith("adr/"):
        raise ToolExecutionError(
            message=f"Unknown doc_type '{doc_type}'.",
            error_code="INVALID_INPUT",
            hint=_DOC_TYPE_HELP,
        )

    if not content:
        raise ToolExecutionError(
            message="content must not be empty.",
            error_code="INVALID_INPUT",
            hint="Provide the full Markdown content for the document.",
        )

    repo = ProjectDocumentRepository(ctx.db)
    doc = await repo.upsert(
        project_id=ctx.project.id,
        doc_type=doc_type,
        content=content,
        title=title,
        agent_id=ctx.agent.id,
    )

    from backend.websocket.manager import ws_manager
    await ws_manager.broadcast_document_updated(
        project_id=ctx.project.id,
        doc_type=doc_type,
        title=title or doc_type,
    )

    chars = len(content)
    return (
        f"Architecture document '{doc_type}' saved ({chars} chars). "
        f"Document ID: {doc.id}. Users can view it on the Architecture page."
    )
