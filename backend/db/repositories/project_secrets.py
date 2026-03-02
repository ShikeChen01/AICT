"""
Project secrets repository — per-project encrypted key-value store for agent use.
"""

from __future__ import annotations

import base64
import uuid
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProjectSecret
from backend.db.repositories.base import BaseRepository
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# When encryption key is missing, values are stored as plaintext (dev only)
_PLAIN_PREFIX = "__plain__"


def _make_fernet(key: str):
    """Build Fernet from a base64-encoded 32-byte key or from a raw key (padded/encoded)."""
    if not key or not key.strip():
        return None
    k = key.strip()
    try:
        decoded = base64.urlsafe_b64decode(k)
        if len(decoded) != 32:
            return None
    except Exception:
        # Use key as seed: hash or pad to 32 bytes and base64 encode
        b = k.encode("utf-8")[:32].ljust(32, b"\0")
        k = base64.urlsafe_b64encode(b).decode("ascii")
    try:
        return Fernet(k)
    except Exception:
        return None


def encrypt_value(plaintext: str, encryption_key: str) -> tuple[str, str | None]:
    """
    Encrypt plaintext for storage. Returns (stored_value, hint).
    If encryption_key is empty, returns (plaintext with prefix, last 4 chars as hint).
    """
    hint = (plaintext[-4:] if len(plaintext) >= 4 else plaintext) if plaintext else None
    if not encryption_key or not encryption_key.strip():
        return (_PLAIN_PREFIX + (plaintext or ""), hint)
    f = _make_fernet(encryption_key)
    if not f:
        return (_PLAIN_PREFIX + (plaintext or ""), hint)
    try:
        encrypted = f.encrypt((plaintext or "").encode("utf-8")).decode("ascii")
        return (encrypted, hint)
    except Exception as e:
        logger.warning("Project secret encryption failed: %s", e)
        return (_PLAIN_PREFIX + (plaintext or ""), hint)


def decrypt_value(stored: str, encryption_key: str) -> str:
    """
    Decrypt stored value. If encryption_key is empty or value has plain prefix, return as-is.
    """
    if not stored:
        return ""
    if stored.startswith(_PLAIN_PREFIX):
        return stored[len(_PLAIN_PREFIX) :]
    if not encryption_key or not encryption_key.strip():
        return stored
    f = _make_fernet(encryption_key)
    if not f:
        return stored
    try:
        return f.decrypt(stored.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning("Project secret decryption failed (invalid token)")
        return ""
    except Exception as e:
        logger.warning("Project secret decryption failed: %s", e)
        return ""


class ProjectSecretsRepository(BaseRepository[ProjectSecret]):
    def __init__(self, session: AsyncSession, encryption_key: str = ""):
        super().__init__(ProjectSecret, session)
        self._encryption_key = encryption_key or ""

    async def list_for_project(self, project_id: UUID) -> list[ProjectSecret]:
        result = await self.session.execute(
            select(ProjectSecret)
            .where(ProjectSecret.project_id == project_id)
            .order_by(ProjectSecret.name)
        )
        return list(result.scalars().all())

    async def get_by_project_and_name(
        self, project_id: UUID, name: str
    ) -> ProjectSecret | None:
        result = await self.session.execute(
            select(ProjectSecret).where(
                ProjectSecret.project_id == project_id,
                ProjectSecret.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, project_id: UUID, name: str, value: str
    ) -> ProjectSecret:
        existing = await self.get_by_project_and_name(project_id, name)
        stored, hint = encrypt_value(value, self._encryption_key)
        if not self._encryption_key or not self._encryption_key.strip():
            logger.warning(
                "Project secrets: SECRET_ENCRYPTION_KEY not set; storing values unencrypted"
            )
        if existing:
            existing.encrypted_value = stored
            existing.hint = hint
            await self.session.flush()
            return existing
        secret = ProjectSecret(
            id=uuid.uuid4(),
            project_id=project_id,
            name=name,
            encrypted_value=stored,
            hint=hint,
        )
        await self.create(secret)
        return secret

    async def delete_by_name(self, project_id: UUID, name: str) -> bool:
        existing = await self.get_by_project_and_name(project_id, name)
        if not existing:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True

    async def get_plaintext_values(self, project_id: UUID) -> dict[str, str]:
        """Load all secrets for a project and return name -> plaintext value (for agent injection)."""
        rows = await self.list_for_project(project_id)
        out: dict[str, str] = {}
        for row in rows:
            out[row.name] = decrypt_value(row.encrypted_value, self._encryption_key)
        return out
