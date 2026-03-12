from __future__ import annotations

from sqlalchemy.engine import make_url

from backend.scripts.upgrade_db import (
    BASELINE_REVISION,
    build_sync_database_url,
    needs_legacy_transition,
)


def test_build_sync_database_url_converts_driver_and_ssl(monkeypatch) -> None:
    monkeypatch.setenv("DB_SSL_MODE", "require")

    sync_url = build_sync_database_url(
        "postgresql+asyncpg://user:pass@example.com:5432/aict"
    )

    parsed = make_url(sync_url)
    assert parsed.drivername == "postgresql+psycopg2"
    assert parsed.username == "user"
    assert parsed.password == "pass"
    assert parsed.host == "example.com"
    assert parsed.database == "aict"
    assert parsed.query["sslmode"] == "require"


def test_needs_legacy_transition_matches_old_chain_only() -> None:
    assert needs_legacy_transition("024_rag_knowledge_base") is True
    assert needs_legacy_transition("029") is True
    assert needs_legacy_transition(BASELINE_REVISION) is False
    assert needs_legacy_transition(None) is False
