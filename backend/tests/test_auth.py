"""
Tests for authentication utilities.
"""

import pytest
from fastapi import HTTPException

from backend.core.auth import verify_agent_request, verify_token, verify_ws_token


# ── verify_token ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    result = await verify_token("Bearer test-secret-token")
    assert result is True


@pytest.mark.asyncio
async def test_invalid_token(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("Bearer wrong-token")
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_missing_bearer_prefix(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("test-secret-token")
    assert exc_info.value.status_code == 401
    assert "Invalid authorization header" in exc_info.value.detail


@pytest.mark.asyncio
async def test_empty_bearer(monkeypatch):
    monkeypatch.setattr("backend.core.auth.settings.api_token", "test-secret-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("Bearer ")
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
async def test_valid_agent_id():
    result = await verify_agent_request("some-agent-uuid")
    assert result == "some-agent-uuid"


@pytest.mark.asyncio
async def test_empty_agent_id():
    with pytest.raises(HTTPException) as exc_info:
        await verify_agent_request("")
    assert exc_info.value.status_code == 401
