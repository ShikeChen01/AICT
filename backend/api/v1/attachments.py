"""
Attachments REST API (Phase 6): upload image files and serve them.

POST /attachments          — multipart upload; returns AttachmentResponse metadata
GET  /attachments/{id}     — returns metadata JSON (no binary)
GET  /attachments/{id}/data — streams raw image bytes with correct Content-Type
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.project_access import require_project_access
from backend.db.models import (
    ALLOWED_ATTACHMENT_MIME_TYPES,
    MAX_ATTACHMENT_SIZE_BYTES,
    User,
)
from backend.db.repositories.attachments import AttachmentRepository
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.schemas.attachment import AttachmentResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

MAX_ATTACHMENTS_PER_UPLOAD = 5  # per request


@router.post(
    "",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    project_id: UUID = Form(..., description="Project the attachment belongs to"),
    file: UploadFile = File(..., description="Image file (JPEG, PNG, GIF, or WebP; max 10 MB)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """Upload an image attachment and return its metadata.

    The binary blob is stored in Postgres (bytea). Call GET .../data to retrieve bytes.
    Members and owners may upload; viewers may not.
    """
    await require_project_access(db, project_id, current_user.id)

    # Validate MIME type
    mime_type = (file.content_type or "").lower()
    if mime_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{mime_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_MIME_TYPES))}"
            ),
        )

    # Read with size guard
    data = await file.read(MAX_ATTACHMENT_SIZE_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB limit.",
        )
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    filename = (file.filename or "upload").strip() or "upload"

    repo = AttachmentRepository(db)
    attachment = await repo.create_attachment(
        project_id=project_id,
        uploaded_by_user_id=current_user.id,
        filename=filename,
        mime_type=mime_type,
        data=data,
    )
    await db.commit()
    await db.refresh(attachment)

    logger.info(
        "upload_attachment: id=%s project=%s size=%d mime=%s user=%s",
        attachment.id,
        project_id,
        len(data),
        mime_type,
        current_user.id,
    )
    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment_metadata(
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """Return attachment metadata (filename, mime_type, size, sha256) — no binary."""
    repo = AttachmentRepository(db)
    attachment = await repo.get_by_id(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    await require_project_access(db, attachment.project_id, current_user.id)
    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}/data")
async def get_attachment_data(
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream the raw image bytes with the original Content-Type.

    The response includes Cache-Control and Content-Disposition headers
    so browsers display the image inline.
    """
    repo = AttachmentRepository(db)
    attachment = await repo.get_by_id(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    await require_project_access(db, attachment.project_id, current_user.id)

    return Response(
        content=attachment.data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{attachment.filename}"',
            "Cache-Control": "private, max-age=3600",
            "X-Content-SHA256": attachment.sha256,
        },
    )
