from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.llm.contracts import LLMMessage, LLMRequest, LLMTool, LLMToolCall
from backend.llm.providers.anthropic_sdk import AnthropicSDKProvider


@pytest.mark.asyncio
async def test_anthropic_provider_parses_text_and_tool_calls() -> None:
    provider = AnthropicSDKProvider(api_key="test-key")
    mocked = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="hello"),
                SimpleNamespace(type="tool_use", id="tc-1", name="search", input={"q": "x"}),
            ],
            _request_id="req_123",
        )
    )
    provider.client.messages.create = mocked

    response = await provider.complete(
        LLMRequest(
            model="claude-opus-4-5-20251101",
            system_prompt="test",
            messages=[LLMMessage(role="user", content="hi")],
            tools=[LLMTool(name="search", description="Search", input_schema={"type": "object"})],
            temperature=0.1,
            max_tokens=64,
        )
    )

    assert response.text == "hello"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "tc-1"
    assert response.request_id == "req_123"
    assert mocked.await_count == 1


@pytest.mark.asyncio
async def test_anthropic_provider_skips_orphan_tool_result() -> None:
    provider = AnthropicSDKProvider(api_key="test-key")
    mocked = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="done")], _request_id=None)
    )
    provider.client.messages.create = mocked

    await provider.complete(
        LLMRequest(
            model="claude-opus-4-5-20251101",
            system_prompt="test",
            messages=[
                LLMMessage(
                    role="assistant",
                    content="",
                    tool_calls=[LLMToolCall(id="tc-1", name="search", input={"q": "x"})],
                ),
                LLMMessage(role="tool", content="result", tool_use_id="tc-mismatch"),
            ],
        )
    )

    kwargs = mocked.await_args.kwargs
    sent_messages = kwargs["messages"]
    # only assistant block should be present because tool_result id is orphaned.
    assert len(sent_messages) == 1
    assert sent_messages[0]["role"] == "assistant"

