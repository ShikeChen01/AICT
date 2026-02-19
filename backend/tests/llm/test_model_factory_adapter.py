from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from backend.graph.model_factory import get_model
from backend.llm.contracts import LLMResponse, LLMToolCall


@pytest.mark.asyncio
async def test_model_factory_adapter_invokes_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    model = get_model(role="manager").bind_tools(
        [SimpleNamespace(name="read_history", description="Read", args_schema=None)]
    )

    async def fake_complete(*_args, **_kwargs):
        return LLMResponse(
            text="ok",
            tool_calls=[LLMToolCall(id="tc-1", name="read_history", input={"limit": 1})],
            provider="anthropic",
            model="claude-opus-4-5-20251101",
        )

    monkeypatch.setattr(model.facade, "complete_from_legacy_messages", fake_complete)

    response = await model.ainvoke([SystemMessage(content="sys"), HumanMessage(content="hello")])
    assert isinstance(response, AIMessage)
    assert response.content == "ok"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "read_history"


@pytest.mark.asyncio
async def test_model_factory_adapter_passes_tool_message(monkeypatch: pytest.MonkeyPatch) -> None:
    model = get_model(role="engineer")

    captured = {}

    async def fake_complete(*_args, **kwargs):
        captured.update(kwargs)
        return LLMResponse(text="ok", tool_calls=[])

    monkeypatch.setattr(model.facade, "complete_from_legacy_messages", fake_complete)

    await model.ainvoke(
        [
            HumanMessage(content="start"),
            AIMessage(content="", tool_calls=[{"id": "tc-1", "name": "x", "args": {}, "type": "tool_call"}]),
            ToolMessage(content="result", tool_call_id="tc-1"),
        ]
    )
    messages = captured["messages"]
    assert any(m.get("role") == "tool" and m.get("tool_use_id") == "tc-1" for m in messages)

