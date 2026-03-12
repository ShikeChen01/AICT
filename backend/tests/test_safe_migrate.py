import backend.scripts.safe_migrate as safe_migrate


def test_choose_target_revision_uses_head_when_pgvector_available():
    assert safe_migrate.choose_target_revision(True) == "head"


def test_choose_target_revision_uses_non_pgvector_head_without_pgvector():
    assert (
        safe_migrate.choose_target_revision(False)
        == safe_migrate.SAFE_FALLBACK_REVISION
    )


def test_main_runs_head_when_pgvector_is_available(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example")
    monkeypatch.setattr(safe_migrate, "inspect_pgvector_available", lambda _: True)
    monkeypatch.setattr(safe_migrate, "run_alembic_upgrade", lambda revision: 0)

    assert safe_migrate.main() == 0


def test_main_uses_non_pgvector_head_when_pgvector_is_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example")
    monkeypatch.setattr(safe_migrate, "inspect_pgvector_available", lambda _: False)

    seen = {}

    def fake_upgrade(revision: str) -> int:
        seen["revision"] = revision
        return 0

    monkeypatch.setattr(safe_migrate, "run_alembic_upgrade", fake_upgrade)

    assert safe_migrate.main() == 0
    assert seen["revision"] == safe_migrate.SAFE_FALLBACK_REVISION
