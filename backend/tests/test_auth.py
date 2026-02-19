"""
Tests for authentication utilities.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.core.auth import (
    verify_agent_request,
    verify_internal_api_token,
    verify_token,
    verify_ws_token,
)


def _mock_request():
    return MagicMock(method="GET", url=MagicMock(path="/test"))


# ── verify_token ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    result = await verify_token(_mock_request(), "Bearer test-secret-token")
    assert result is True


@pytest.mark.asyncio
async def test_invalid_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(_mock_request(), "Bearer wrong-token")
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_missing_bearer_prefix(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(_mock_request(), "test-secret-token")
    assert exc_info.value.status_code == 401
    assert "Invalid authorization header" in exc_info.value.detail


@pytest.mark.asyncio
async def test_empty_bearer(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(_mock_request(), "Bearer ")
    assert exc_info.value.status_code == 401


# ── verify_ws_token ─────────────────────────────────────────────────


def test_valid_ws_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "ws-token")
    assert verify_ws_token("ws-token") is True


def test_invalid_ws_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "ws-token")
    assert verify_ws_token("wrong") is False


def test_none_ws_token():
    assert verify_ws_token(None) is False


# ── verify_agent_request ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_internal_api_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "internal-secret")
    result = await verify_internal_api_token(_mock_request(), "Bearer internal-secret")
    assert result is True


@pytest.mark.asyncio
async def test_invalid_internal_api_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "internal-secret")
    with pytest.raises(HTTPException) as exc_info:
        await verify_internal_api_token(_mock_request(), "Bearer wrong")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_agent_id():
    result = await verify_agent_request(True, "00000000-0000-0000-0000-000000000001")
    assert result == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_invalid_agent_id():
    with pytest.raises(HTTPException) as exc_info:
        await verify_agent_request(True, "not-a-uuid")
    assert exc_info.value.status_code == 401
