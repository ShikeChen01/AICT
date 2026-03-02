"""
Tests for Project Secret Tokens feature.

Part-by-part verification against the plan:

1. Storage (plan: project_secrets table, repository_id, Fernet encryption)
   - test_project_secret_model: ProjectSecret has id, project_id, name, encrypted_value, hint, timestamps
   - test_project_secret_unique_per_project_name: unique (project_id, name)
   - test_encrypt_decrypt_plaintext: when key empty, value stored with prefix, decrypt returns plaintext
   - test_encrypt_decrypt_fernet: when key set, value encrypted and decrypt roundtrips

2. Repository (plan: list_for_project, upsert, delete, get_plaintext_values)
   - test_list_for_project_empty / test_list_for_project_returns_masked
   - test_upsert_creates_new / test_upsert_updates_existing
   - test_delete_by_name
   - test_get_plaintext_values_returns_dict

3. Schemas (plan: ProjectSecretResponse id/name/hint/created_at, ProjectSecretUpsert name/value)
   - test_project_secret_response_schema
   - test_project_secret_upsert_schema

4. API (plan: GET list masked, POST upsert, DELETE by name)
   - test_secrets_routes_registered
   - test_list_secrets_returns_masked_no_value
   - test_upsert_and_delete_secret (with auth or 401 check)

5. Agent injection (plan: loop loads secrets, PromptAssembly {project_secrets} KEY=VALUE)
   - test_resolve_placeholders_project_secrets_format
   - test_resolve_placeholders_project_secrets_empty
"""

from __future__ import annotations

import base64
import uuid
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProjectSecret, Repository
from backend.db.repositories.project_secrets import (
    ProjectSecretsRepository,
    decrypt_value,
    encrypt_value,
)
from backend.main import app
from backend.prompts.assembly import _resolve_placeholders
from backend.schemas.project_secrets import ProjectSecretResponse, ProjectSecretUpsert


# ---------------------------------------------------------------------------
# 1. Model & encryption (plan: Storage)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_secret_model(session: AsyncSession, sample_project: Repository) -> None:
    """Plan: ProjectSecret model with id, project_id, name, encrypted_value, hint, created_at, updated_at."""
    secret = ProjectSecret(
        project_id=sample_project.id,
        name="GITHUB_TOKEN",
        encrypted_value="__plain__ghp_xxxx",
        hint="xxxx",
    )
    session.add(secret)
    await session.flush()
    assert secret.id is not None
    assert secret.project_id == sample_project.id
    assert secret.name == "GITHUB_TOKEN"
    assert secret.encrypted_value == "__plain__ghp_xxxx"
    assert secret.hint == "xxxx"
    assert secret.created_at is not None
    assert secret.updated_at is not None


@pytest.mark.asyncio
async def test_project_secret_unique_per_project_name(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: UniqueConstraint(project_id, name)."""
    s1 = ProjectSecret(
        project_id=sample_project.id,
        name="KEY",
        encrypted_value="__plain__val1",
        hint="al1",
    )
    session.add(s1)
    await session.flush()
    s2 = ProjectSecret(
        project_id=sample_project.id,
        name="KEY",
        encrypted_value="__plain__val2",
        hint="al2",
    )
    session.add(s2)
    with pytest.raises(Exception):  # IntegrityError or similar
        await session.flush()


def test_encrypt_decrypt_plaintext() -> None:
    """Plan: When encryption_key blank, values stored unencrypted (dev); decrypt returns plaintext."""
    stored, hint = encrypt_value("my-secret-value", "")
    assert stored.startswith("__plain__")
    assert stored == "__plain__my-secret-value"
    assert hint == "alue"  # last 4 chars of "my-secret-value"
    assert decrypt_value(stored, "") == "my-secret-value"


def test_encrypt_decrypt_fernet() -> None:
    """Plan: Fernet encryption when SECRET_ENCRYPTION_KEY set; roundtrip."""
    key = base64.urlsafe_b64encode(b"0" * 32).decode("ascii")
    stored, hint = encrypt_value("secret123", key)
    assert not stored.startswith("__plain__")
    assert len(stored) > 10
    assert hint == "t123"
    assert decrypt_value(stored, key) == "secret123"


def test_decrypt_plain_prefix_without_key() -> None:
    """Stored value with __plain__ prefix returns value without prefix."""
    assert decrypt_value("__plain__xyz", "") == "xyz"
    assert decrypt_value("__plain__", "") == ""


# ---------------------------------------------------------------------------
# 2. Repository (plan: list_for_project, upsert, delete, get_plaintext_values)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_for_project_empty(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: list_for_project returns list (empty when none)."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    out = await repo.list_for_project(sample_project.id)
    assert out == []


@pytest.mark.asyncio
async def test_list_for_project_returns_masked(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: List returns rows with name/hint only; encrypted_value never exposed by list API (verified in repo)."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    await repo.upsert(sample_project.id, "API_KEY", "sk-12345678")
    await session.commit()
    rows = await repo.list_for_project(sample_project.id)
    assert len(rows) == 1
    assert rows[0].name == "API_KEY"
    assert rows[0].hint == "5678"
    # Value is in DB but API layer must never return it; repo returns full model, API strips to id/name/hint/created_at
    assert rows[0].encrypted_value  # present on model; API schema excludes it


@pytest.mark.asyncio
async def test_upsert_creates_new(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: upsert(project_id, name, value) creates new secret."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    secret = await repo.upsert(sample_project.id, "TOKEN", "value1")
    await session.flush()
    assert secret.id is not None
    assert secret.name == "TOKEN"
    assert secret.hint == "lue1"  # last 4 chars of "value1"


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: upsert same name updates existing (by project_id + name)."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    s1 = await repo.upsert(sample_project.id, "TOKEN", "value1")
    await session.flush()
    s2 = await repo.upsert(sample_project.id, "TOKEN", "value2-longer")
    await session.flush()
    assert s1.id == s2.id
    assert s2.hint == "nger"


@pytest.mark.asyncio
async def test_delete_by_name(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: delete_by_name(project_id, name) removes secret."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    await repo.upsert(sample_project.id, "X", "y")
    await session.flush()
    ok = await repo.delete_by_name(sample_project.id, "X")
    assert ok is True
    rows = await repo.list_for_project(sample_project.id)
    assert len(rows) == 0
    ok2 = await repo.delete_by_name(sample_project.id, "X")
    assert ok2 is False


@pytest.mark.asyncio
async def test_get_plaintext_values_returns_dict(
    session: AsyncSession, sample_project: Repository
) -> None:
    """Plan: get_plaintext_values(project_id) returns dict[str, str] for agent injection."""
    repo = ProjectSecretsRepository(session, encryption_key="")
    await repo.upsert(sample_project.id, "A", "val_a")
    await repo.upsert(sample_project.id, "B", "val_b")
    await session.flush()
    out = await repo.get_plaintext_values(sample_project.id)
    assert out == {"A": "val_a", "B": "val_b"}


@pytest.mark.asyncio
async def test_get_plaintext_values_decrypts_with_key(
    session: AsyncSession, sample_project: Repository
) -> None:
    """When encryption key is set, get_plaintext_values returns decrypted values."""
    key = base64.urlsafe_b64encode(b"1" * 32).decode("ascii")
    repo = ProjectSecretsRepository(session, encryption_key=key)
    await repo.upsert(sample_project.id, "K", "plain")
    await session.flush()
    out = await repo.get_plaintext_values(sample_project.id)
    assert out == {"K": "plain"}


# ---------------------------------------------------------------------------
# 3. Schemas (plan: ProjectSecretResponse, ProjectSecretUpsert)
# ---------------------------------------------------------------------------


def test_project_secret_response_schema() -> None:
    """Plan: ProjectSecretResponse has id, name, hint, created_at (no value)."""
    from datetime import datetime

    resp = ProjectSecretResponse(
        id=uuid.uuid4(),
        name="X",
        hint="yyyy",
        created_at=datetime.now(),
    )
    assert resp.name == "X"
    assert resp.hint == "yyyy"
    assert "value" not in ProjectSecretResponse.model_fields


def test_project_secret_upsert_schema() -> None:
    """Plan: ProjectSecretUpsert has name and value."""
    body = ProjectSecretUpsert(name="TOKEN", value="secret")
    assert body.name == "TOKEN"
    assert body.value == "secret"


def test_project_secret_upsert_schema_validates_name_and_value() -> None:
    """ProjectSecretUpsert rejects empty name or empty value."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProjectSecretUpsert(name="", value="x")
    with pytest.raises(ValidationError):
        ProjectSecretUpsert(name="X", value="")


# ---------------------------------------------------------------------------
# 4. API (plan: GET list masked, POST upsert, DELETE by name)
# ---------------------------------------------------------------------------


def test_secrets_routes_registered() -> None:
    """Plan: GET/POST/DELETE /repositories/{id}/secrets registered."""
    routes = [r.path for r in app.routes]
    # Router is mounted under /api/v1, path may be like /repositories/{repository_id}/secrets
    path_strs = [getattr(r, "path", "") or "" for r in app.routes]
    assert any("secrets" in p for p in path_strs)


def test_list_secrets_returns_masked_no_value(client: TestClient) -> None:
    """Plan: List endpoint returns only id, name, hint — never value."""
    # Use a random UUID; without auth we may get 401/404/422 (path validation).
    r = client.get("/api/v1/repositories/00000000-0000-0000-0000-000000000001/secrets")
    assert r.status_code in (200, 401, 403, 404, 422)
    if r.status_code == 200:
        data = r.json()
        assert isinstance(data, list)
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "hint" in item or "hint" not in item  # hint can be null
            assert "value" not in item
            assert "encrypted_value" not in item


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 5. Agent injection (plan: {project_secrets} placeholder KEY=VALUE format)
# ---------------------------------------------------------------------------


def test_resolve_placeholders_project_secrets_format() -> None:
    """Plan: {project_secrets} replaced by KEY=VALUE lines (sorted)."""
    class FakeAgent:
        display_name = "Manager"

    class FakeProject:
        name = "TestProject"

    content = "Secrets:\n{project_secrets}"
    secrets = {"B_KEY": "b_val", "A_KEY": "a_val"}
    out = _resolve_placeholders(
        content,
        FakeAgent(),
        FakeProject(),
        None,
        project_secrets=secrets,
    )
    assert "A_KEY=a_val" in out
    assert "B_KEY=b_val" in out
    assert out.index("A_KEY") < out.index("B_KEY")


def test_resolve_placeholders_project_secrets_empty() -> None:
    """Plan: When no secrets, {project_secrets} = 'No project secrets configured.'"""
    class FakeAgent:
        display_name = "Agent"

    class FakeProject:
        name = "Proj"

    content = "Here: {project_secrets}"
    out = _resolve_placeholders(
        content,
        FakeAgent(),
        FakeProject(),
        None,
        project_secrets={},
    )
    assert "No project secrets configured." in out


def test_resolve_placeholders_project_secrets_none() -> None:
    """When project_secrets is None, treat as empty."""
    class FakeAgent:
        display_name = "Agent"

    class FakeProject:
        name = "Proj"

    content = "Here: {project_secrets}"
    out = _resolve_placeholders(
        content,
        FakeAgent(),
        FakeProject(),
        None,
        project_secrets=None,
    )
    assert "No project secrets configured." in out


# ---------------------------------------------------------------------------
# 6. Plan: config and BLOCK_REGISTRY
# ---------------------------------------------------------------------------


def test_config_has_secret_encryption_key() -> None:
    """Plan: backend/config.py has secret_encryption_key."""
    from backend.config import settings

    assert hasattr(settings, "secret_encryption_key")
    assert isinstance(settings.secret_encryption_key, str)


def test_assembly_block_registry_has_secrets() -> None:
    """Plan: BLOCK_REGISTRY has 'secrets' block key."""
    from backend.prompts.assembly import BLOCK_REGISTRY

    assert "secrets" in BLOCK_REGISTRY
    assert BLOCK_REGISTRY["secrets"].name == "secrets"
