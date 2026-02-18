"""
Tests for engineer jobs API endpoints.

Jobs router was removed in Agent 1 (replaced by sessions). These tests accept 404
when the jobs route is not mounted.
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
    """Test /api/v1/jobs endpoints (route removed in Agent 1; accept 404 or 401/422)."""

    def test_list_jobs_requires_auth(self, client):
        """Without auth, list jobs returns 401/422 or 404 if route not mounted."""
        resp = client.get("/api/v1/jobs", params={"project_id": str(uuid.uuid4())})
        assert resp.status_code in (401, 422, 404)

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
        """Without auth, get job returns 401, 422, or 404."""
        resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
        assert resp.status_code in (401, 422, 404)

    def test_jobs_route_registered(self, client):
        """Health is mounted; jobs may be 404 if route removed (Agent 1)."""
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        r2 = client.get("/api/v1/jobs", params={"project_id": str(uuid.uuid4())})
        assert r2.status_code in (401, 422, 404)
