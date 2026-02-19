from __future__ import annotations

import pytest

from backend.llm.cloud_facade import CloudLLMFacade
from backend.llm.contracts import LLMMessage, LLMRequest, LLMResponse, LLMTool, LLMToolCall
from backend.llm.tool_name_adapter import ToolNameAdapter, sanitize_tool_name


def test_sanitize_tool_name_replaces_invalid_chars() -> None:
    assert sanitize_tool_name("execute command E2B") == "execute_command_E2B"
    assert sanitize_tool_name("tool@name!") == "tool_name"


def test_adapter_disambiguates_collisions() -> None:
    adapter = ToolNameAdapter()
    first = adapter.to_canonical("tool name")
    second = adapter.to_canonical("tool@name")

    assert first == "tool_name"
    assert second == "tool_name_2"
    assert adapter.to_original(first) == "tool name"
    assert adapter.to_original(second) == "tool@name"


@pytest.mark.asyncio
async def test_cloud_facade_round_trips_tool_names(monkeypatch: pytest.MonkeyPatch) -> None:
    facade = CloudLLMFacade()
    captured: dict[str, LLMRequest] = {}

    class _FakeProvider:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            captured["request"] = request
            return LLMResponse(
                text="ok",
                tool_calls=[
                    LLMToolCall(
                        id="tc-1",
                        name=request.tools[0].name,
                        input={"command": "pwd"},
                    )
                ],
                provider="google",
                model=request.model,
            )

    monkeypatch.setattr(facade.router, "get_provider", lambda *_args, **_kwargs: _FakeProvider())

    response = await facade.complete(
        LLMRequest(
            model="gemini-2.0-flash",
            system_prompt="test",
            tools=[LLMTool(name="execute command E2B", description="run", input_schema={"type": "object"})],
            messages=[
                LLMMessage(
                    role="assistant",
                    content="",
                    tool_calls=[LLMToolCall(id="tc-1", name="execute command E2B", input={"command": "pwd"})],
                )
            ],
        )
    )

    assert captured["request"].tools[0].name == "execute_command_E2B"
    assert captured["request"].messages[0].tool_calls[0].name == "execute_command_E2B"
    assert response.tool_calls[0].name == "execute command E2B"
