from __future__ import annotations

from sqlalchemy.engine import make_url

import backend.scripts.upgrade_db as upgrade_db


class FakeResult:
    def __init__(self, rows: list[dict] | None = None, scalar_value=None) -> None:
        self._rows = rows or []
        self._scalar_value = scalar_value

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar_value

    def __iter__(self):
        return iter(self._rows)


class RecordingConnection:
    def __init__(self, *, agent_rows: list[dict]) -> None:
        self.agent_rows = agent_rows
        self.executed: list[tuple[str, dict | None]] = []
        self.insert_params: list[dict] = []

    def execute(self, statement, params=None) -> FakeResult:
        sql = str(statement)
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))

        if "FROM agents a" in normalized and "LEFT JOIN sandbox_configs sc" in normalized:
            return FakeResult(self.agent_rows)

        if "INSERT INTO sandbox (" in normalized:
            self.insert_params.append(params)
            return FakeResult()

        if normalized.startswith("ALTER TABLE agents DROP COLUMN IF EXISTS"):
            return FakeResult()

        raise AssertionError(f"Unexpected SQL: {normalized}")


def test_build_sync_database_url_converts_driver_and_ssl(monkeypatch) -> None:
    monkeypatch.setenv("DB_SSL_MODE", "require")

    sync_url = upgrade_db.build_sync_database_url(
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
    assert upgrade_db.needs_legacy_transition("024_rag_knowledge_base") is True
    assert upgrade_db.needs_legacy_transition("029") is True
    assert upgrade_db.needs_legacy_transition(upgrade_db.BASELINE_REVISION) is False
    assert upgrade_db.needs_legacy_transition(None) is False


def test_migrate_agent_sandbox_columns_defaults_when_config_os_image_is_null(monkeypatch) -> None:
    """Config row exists but os_image is NULL — should fall back to ubuntu-22.04."""
    conn = RecordingConnection(
        agent_rows=[
            {
                "agent_id": "agent-1",
                "project_id": "project-1",
                "sandbox_config_id": "cfg-1",
                "sandbox_id": "orch-1",
                "sandbox_persist": False,
                "os_image": None,
                "setup_script": None,
            }
        ],
    )

    monkeypatch.setattr(
        upgrade_db,
        "has_column",
        lambda _conn, table_name, column_name: table_name == "agents"
        and column_name in {"sandbox_id", "sandbox_persist"},
    )

    upgrade_db.migrate_agent_sandbox_columns(conn)

    assert conn.insert_params[0]["os_image"] == "ubuntu-22.04"
    assert conn.insert_params[0]["setup_script"] is None
    assert any("sc.os_image" in sql for sql, _ in conn.executed), "JOIN query should reference sc.os_image"


def test_migrate_agent_sandbox_columns_copies_present_config_fields(monkeypatch) -> None:
    """Config row has both os_image and setup_script — values should be copied verbatim."""
    conn = RecordingConnection(
        agent_rows=[
            {
                "agent_id": "agent-1",
                "project_id": "project-1",
                "sandbox_config_id": "cfg-1",
                "sandbox_id": "orch-1",
                "sandbox_persist": True,
                "os_image": "ubuntu-24.04",
                "setup_script": "echo ready",
            }
        ],
    )

    monkeypatch.setattr(
        upgrade_db,
        "has_column",
        lambda _conn, table_name, column_name: table_name == "agents"
        and column_name in {"sandbox_id", "sandbox_persist"},
    )

    upgrade_db.migrate_agent_sandbox_columns(conn)

    assert conn.insert_params[0]["os_image"] == "ubuntu-24.04"
    assert conn.insert_params[0]["setup_script"] == "echo ready"
    assert conn.insert_params[0]["persistent"] is True
