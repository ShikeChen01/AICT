from __future__ import annotations

from typing import Any

import pytest

from backend.services.llm_service import LLMService


class _FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeClient:
    def __init__(self, captured: dict[str, Any], response: _FakeResponse):
        self._captured = captured
        self._response = response

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self._captured["url"] = url
        self._captured["payload"] = json
        return self._response


@pytest.mark.asyncio
async def test_google_with_tools_omits_empty_model_message_and_tools_when_no_declarations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_response = _FakeResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )
    monkeypatch.setattr(
        "backend.services.llm_service.httpx.AsyncClient",
        lambda timeout: _FakeClient(captured, fake_response),
    )

    service = LLMService(timeout_seconds=5)
    text, _tool_calls = await service._call_google_with_tools(
        model="gemini-2.0-flash",
        system_prompt="test",
        messages=[{"role": "assistant", "content": "", "tool_calls": []}],
        tools=[],
    )

    assert text == "ok"
    payload = captured["payload"]
    assert "tools" not in payload
    assert payload["contents"] == [{"role": "user", "parts": [{"text": ""}]}]


@pytest.mark.asyncio
async def test_google_with_tools_skips_malformed_function_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_response = _FakeResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )
    monkeypatch.setattr(
        "backend.services.llm_service.httpx.AsyncClient",
        lambda timeout: _FakeClient(captured, fake_response),
    )

    service = LLMService(timeout_seconds=5)
    text, _tool_calls = await service._call_google_with_tools(
        model="gemini-2.0-flash",
        system_prompt="test",
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "bad-1", "name": "", "input": {"x": 1}},
                    {"id": "good-1", "name": "execute_command", "input": {"command": "pwd"}},
                ],
            }
        ],
        tools=[{"name": "execute_command", "description": "", "input_schema": {"type": "object"}}],
    )

    assert text == "ok"
    parts = captured["payload"]["contents"][0]["parts"]
    assert len(parts) == 1
    assert parts[0]["functionCall"]["name"] == "execute_command"


@pytest.mark.asyncio
async def test_google_without_tools_uses_fallback_content_for_empty_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_response = _FakeResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )
    monkeypatch.setattr(
        "backend.services.llm_service.httpx.AsyncClient",
        lambda timeout: _FakeClient(captured, fake_response),
    )

    service = LLMService(timeout_seconds=5)
    text = await service._call_google(
        model="gemini-2.0-flash",
        system_prompt="test",
        messages=[],
    )

    assert text == "ok"
    assert captured["payload"]["contents"] == [{"role": "user", "parts": [{"text": ""}]}]
