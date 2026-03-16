"""Integration tests for pool manager v4 API.

These test the FastAPI endpoints with mocked Docker and VM backends.
Verifies the full request → budget → pool state → response cycle.
"""

import sys
import os
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set up env before importing the app
os.environ["MASTER_TOKEN"] = "test-token"
os.environ["STATE_FILE"] = ""  # Will be overridden per test


@pytest.fixture(autouse=True)
def _temp_state(tmp_path, monkeypatch):
    """Give each test its own state file."""
    state_file = str(tmp_path / "state.json")
    monkeypatch.setenv("STATE_FILE", state_file)
    monkeypatch.setattr("config.STATE_FILE", state_file)


@pytest.fixture
def mock_docker():
    """Mock DockerManager so no real Docker daemon is needed."""
    with patch("main.DockerManager") as MockDocker:
        instance = MagicMock()
        instance.create_container.return_value = "container-id-fake"
        instance.ensure_volume.return_value = None
        instance.is_running.return_value = True
        instance.list_sandbox_containers.return_value = []
        instance.reset_container.return_value = "container-id-reset"
        instance.destroy_container.return_value = None
        instance.remove_volume.return_value = None
        MockDocker.return_value = instance
        yield instance


@pytest.fixture
def mock_vm():
    """Mock VMManager."""
    with patch("main._VM_AVAILABLE", True), \
         patch("main.VMManager") as MockVM:
        instance = MagicMock()
        instance.create_vm.return_value = "aict-vm-fake"
        instance.is_running.return_value = True
        instance.migrate_files_to_vm.return_value = True
        instance.migrate_files_from_vm.return_value = True
        instance._static_ip_for_port = MagicMock(return_value="192.168.100.10")
        MockVM.return_value = instance
        MockVM._static_ip_for_port = MagicMock(return_value="192.168.100.10")
        yield instance


@pytest.fixture
def mock_wait_ready():
    """Mock _wait_for_ready to always return True (no real HTTP probing)."""
    with patch("main._wait_for_ready", return_value=True) as m:
        yield m


@pytest.fixture
def client(mock_docker, mock_vm, mock_wait_ready):
    """Create a TestClient with mocked backends."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer test-token"}
_agent_counter = 0


def _agent_id():
    """Generate unique agent IDs for each test call."""
    global _agent_counter
    _agent_counter += 1
    return f"agent-test-{_agent_counter}"


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/health", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_requires_auth(self, client, monkeypatch):
        monkeypatch.setattr("config.MASTER_TOKEN", "test-token")
        resp = client.get("/api/health")
        assert resp.status_code == 401


# ── Session Start ────────────────────────────────────────────────────────────


class TestSessionStart:
    def test_headless_session(self, client, mock_docker):
        aid = _agent_id()
        resp = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False, "requires_desktop": False},
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "sandbox_id" in data
        assert data["unit_type"] == "headless"
        assert data["host_port"] >= 30001
        assert data["created"] is True
        assert "host" in data  # v4: host field for backend integration
        assert isinstance(data["host"], str)
        assert "auth_token" in data
        mock_docker.create_container.assert_called_once()

    def test_desktop_session(self, client, mock_vm):
        aid = _agent_id()
        resp = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": True, "requires_desktop": True},
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["unit_type"] == "desktop"
        assert data["host_port"] >= 30051
        assert data["created"] is True
        assert "host" in data
        assert "auth_token" in data
        mock_vm.create_vm.assert_called_once()

    def test_session_without_agent_id(self, client, mock_docker):
        """Backend may create sandbox before assigning an agent."""
        resp = client.post(
            "/api/sandbox/session/start",
            json={"persistent": False},
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "sandbox_id" in data
        assert data["created"] is True
        assert "host" in data

    def test_backward_compat_defaults_to_headless(self, client, mock_docker):
        """Request without requires_desktop defaults to headless."""
        aid = _agent_id()
        resp = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )
        assert resp.status_code == 201
        assert resp.json()["unit_type"] == "headless"

    def test_existing_agent_returns_same_unit(self, client, mock_docker):
        """If agent already has a unit, return it instead of creating a new one."""
        aid = _agent_id()
        r1 = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )
        assert r1.status_code == 201
        sid1 = r1.json()["sandbox_id"]

        r2 = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )
        assert r2.status_code == 200
        assert r2.json()["sandbox_id"] == sid1
        assert r2.json()["created"] is False
        assert "host" in r2.json()  # v4: always include host


# ── Session End ──────────────────────────────────────────────────────────────


class TestSessionEnd:
    def test_session_end(self, client, mock_docker):
        aid = _agent_id()
        start = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )
        assert start.status_code == 201

        end = client.post(
            "/api/sandbox/session/end",
            json={"agent_id": aid},
            headers=AUTH,
        )
        assert end.status_code == 200
        assert end.json()["ok"] is True

    def test_session_end_nonexistent_agent(self, client):
        """Ending a session for an unknown agent should succeed gracefully."""
        end = client.post(
            "/api/sandbox/session/end",
            json={"agent_id": "ghost-agent"},
            headers=AUTH,
        )
        assert end.status_code == 200


# ── Capacity Status ──────────────────────────────────────────────────────────


class TestCapacityStatus:
    def test_status_endpoint(self, client):
        resp = client.get("/api/status", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "budget" in data
        budget = data["budget"]
        assert "cpu" in budget
        assert "headless" in budget
        assert "can_add_headless" in budget

    def test_status_reflects_provisioned_units(self, client, mock_docker):
        aid = _agent_id()
        client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )

        resp = client.get("/api/status", headers=AUTH)
        data = resp.json()
        assert data["budget"]["headless"]["count"] == 1


# ── Units List ───────────────────────────────────────────────────────────────


class TestUnitsList:
    def test_units_endpoint(self, client, mock_docker):
        a1, a2 = _agent_id(), _agent_id()
        client.post(
            "/api/sandbox/session/start",
            json={"agent_id": a1, "persistent": False},
            headers=AUTH,
        )
        client.post(
            "/api/sandbox/session/start",
            json={"agent_id": a2, "persistent": False},
            headers=AUTH,
        )

        resp = client.get("/api/units", headers=AUTH)
        assert resp.status_code == 200
        units = resp.json()
        assert len(units) == 2


# ── Touch ────────────────────────────────────────────────────────────────────


class TestTouch:
    def test_touch_resets_idle(self, client, mock_docker):
        aid = _agent_id()
        start = client.post(
            "/api/sandbox/session/start",
            json={"agent_id": aid, "persistent": False},
            headers=AUTH,
        )
        sid = start.json()["sandbox_id"]

        resp = client.post(f"/api/sandbox/{sid}/touch", headers=AUTH)
        assert resp.status_code == 200
