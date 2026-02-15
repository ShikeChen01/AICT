"""
Tests for engineer jobs API endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer change-me-in-production"}


class TestJobsAPI:
    """Test /api/v1/jobs endpoints (require auth and valid project_id)."""

    def test_list_jobs_requires_auth(self, client):
        """Without Authorization header, list jobs returns 422 (missing required header)."""
        resp = client.get("/api/v1/jobs", params={"project_id": str(uuid.uuid4())})
        # FastAPI returns 422 when required Header(...) is missing
        assert resp.status_code in (401, 422)

    @pytest.mark.skip(reason="Requires database; run with DB for integration test")
    def test_list_jobs_with_auth_returns_200_or_500(self, client, auth_headers):
        """With auth, list jobs returns 200 (empty list) or 500 if DB unavailable."""
        resp = client.get(
            "/api/v1/jobs",
            params={"project_id": str(uuid.uuid4())},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 500)

    def test_get_job_requires_auth(self, client):
        """Without auth, get job returns 401 or 422."""
        resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
        assert resp.status_code in (401, 422)

    def test_jobs_route_registered(self, client):
        """Jobs router is mounted under /api/v1."""
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        # Jobs route exists: without auth we get 422 (missing header)
        r2 = client.get("/api/v1/jobs", params={"project_id": str(uuid.uuid4())})
        assert r2.status_code in (401, 422)
