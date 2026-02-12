"""
Tests for FastAPI app — health checks, CORS, routing.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoints:
    def test_public_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_internal_health(self, client):
        resp = client.get("/internal/agent/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCORS:
    def test_cors_headers_present(self, client):
        resp = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in resp.headers


class TestRouting:
    def test_unknown_route_returns_404(self, client):
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
