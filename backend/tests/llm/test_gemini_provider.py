from __future__ import annotations

from typing import Any

import pytest

from backend.llm.contracts import LLMMessage, LLMRequest, LLMToolCall
from backend.llm.providers.gemini_sdk import GeminiProviderAdapter


class _FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

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
async def test_gemini_provider_maps_tool_result_to_function_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_response = _FakeResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "ok"}],
                    }
                }
            ]
        },
    )
    monkeypatch.setattr(
        "backend.llm.providers.gemini_sdk.httpx.AsyncClient",
        lambda timeout: _FakeClient(captured, fake_response),
    )

    provider = GeminiProviderAdapter(api_key="test-key")
    request = LLMRequest(
        model="gemini-2.0-flash",
        system_prompt="test",
        messages=[
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[LLMToolCall(id="tc-1", name="execute_command", input={"command": "pwd"})],
            ),
            LLMMessage(role="tool", content="Exit Code: 0", tool_use_id="tc-1"),
        ],
    )

    response = await provider.complete(request)

    assert response.text == "ok"
    parts = captured["payload"]["contents"][1]["parts"]
    function_response = parts[0]["functionResponse"]
    assert function_response["name"] == "execute_command"
    assert function_response["id"] == "tc-1"


@pytest.mark.asyncio
async def test_gemini_provider_skips_orphan_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    fake_response = _FakeResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "ok"}],
                    }
                }
            ]
        },
    )
    monkeypatch.setattr(
        "backend.llm.providers.gemini_sdk.httpx.AsyncClient",
        lambda timeout: _FakeClient(captured, fake_response),
    )

    provider = GeminiProviderAdapter(api_key="test-key")
    request = LLMRequest(
        model="gemini-2.0-flash",
        system_prompt="test",
        messages=[LLMMessage(role="tool", content="orphan", tool_use_id="unknown-id")],
    )

    await provider.complete(request)

    # Orphan tool message should be dropped; request must still include contents to avoid 400.
    assert captured["payload"]["contents"] == [{"role": "user", "parts": [{"text": ""}]}]
