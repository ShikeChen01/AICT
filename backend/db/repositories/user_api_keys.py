"""
Per-user LLM API key repository — encrypted CRUD.

Uses the same Fernet encryption as ProjectSecretsRepository.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import UserAPIKey
from backend.db.repositories.project_secrets import encrypt_value, decrypt_value
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

VALID_PROVIDERS = {"anthropic", "openai", "google", "moonshot"}


class UserAPIKeyRepository:
    def __init__(self, session: AsyncSession, encryption_key: str = ""):
        self._db = session
        self._encryption_key = encryption_key or ""

    async def list_for_user(self, user_id: UUID) -> list[UserAPIKey]:
        result = await self._db.execute(
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user_id)
            .order_by(UserAPIKey.provider)
        )
        return list(result.scalars().all())

    async def get_by_provider(self, user_id: UUID, provider: str) -> UserAPIKey | None:
        result = await self._db.execute(
            select(UserAPIKey).where(
                UserAPIKey.user_id == user_id,
                UserAPIKey.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: UUID, provider: str, plaintext_key: str) -> UserAPIKey:
        """Create or update a user's API key for a provider."""
        stored, _ = encrypt_value(plaintext_key, self._encryption_key)
        hint = plaintext_key[-3:] if len(plaintext_key) >= 3 else plaintext_key

        existing = await self.get_by_provider(user_id, provider)
        if existing:
            existing.encrypted_key = stored
            existing.display_hint = f"...{hint}"
            existing.is_valid = True
            await self._db.flush()
            return existing

        key = UserAPIKey(
            id=uuid.uuid4(),
            user_id=user_id,
            provider=provider,
            encrypted_key=stored,
            display_hint=f"...{hint}",
        )
        self._db.add(key)
        await self._db.flush()
        return key

    async def get_decrypted_key(self, user_id: UUID, provider: str) -> str | None:
        """Get the plaintext API key for a user+provider. Returns None if not found."""
        row = await self.get_by_provider(user_id, provider)
        if not row:
            return None
        if not row.is_valid:
            return None
        return decrypt_value(row.encrypted_key, self._encryption_key)

    async def mark_invalid(self, user_id: UUID, provider: str) -> None:
        """Mark a key as invalid (e.g. after auth error from provider)."""
        row = await self.get_by_provider(user_id, provider)
        if row:
            row.is_valid = False
            await self._db.flush()

    async def delete_key(self, user_id: UUID, provider: str) -> bool:
        row = await self.get_by_provider(user_id, provider)
        if not row:
            return False
        await self._db.delete(row)
        await self._db.flush()
        return True
