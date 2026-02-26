"""
Regression tests: LLMService._select_provider correctly routes gpt-* and o* models
to the 'openai' provider, and all non-legacy-mode calls go through the facade.
"""

from __future__ import annotations

import pytest

from backend.services.llm_service import LLMService


# ---------------------------------------------------------------------------
# _select_provider routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        # Anthropic
        ("claude-opus-4-6", "anthropic"),
        ("claude-sonnet-4-6", "anthropic"),
        # Google
        ("gemini-2.5-flash", "google"),
        # OpenAI gpt-* series
        ("gpt-5.2", "openai"),
    ],
)
def test_select_provider_routing(
    model: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "sk-ant-test")
    monkeypatch.setattr(config.settings, "gemini_api_key", "gm-test")
    monkeypatch.setattr(config.settings, "openai_api_key", "sk-oai-test")

    provider = LLMService._select_provider(model)
    assert provider == expected, f"model={model!r}: expected {expected!r}, got {provider!r}"


def test_select_provider_falls_back_to_anthropic_when_no_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "sk-ant-test")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "openai_api_key", "")

    # Unknown model with no openai key should fall back to anthropic
    provider = LLMService._select_provider("some-unknown-model")
    assert provider == "anthropic"


def test_select_provider_returns_none_when_no_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "openai_api_key", "")

    assert LLMService._select_provider("gpt-4o") == "none"
    assert LLMService._select_provider("o3") == "none"
    assert LLMService._select_provider("claude-3") == "none"


# ---------------------------------------------------------------------------
# chat_completion_with_tools routes through facade for all providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_routes_openai_through_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI models must call the facade, not a legacy direct-HTTP method."""
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "openai_api_key", "sk-oai-test")
    monkeypatch.setattr(config.settings, "llm_use_legacy_http", False)

    facade_calls: list[dict] = []

    from backend.llm.contracts import LLMResponse

    async def fake_complete_from_legacy_messages(**kwargs):
        facade_calls.append(kwargs)
        return LLMResponse(
            text="Hello from OpenAI",
            tool_calls=[],
            provider="openai",
            model=kwargs["model"],
            request_id="req-test",
        )

    svc = LLMService()
    monkeypatch.setattr(svc._facade, "complete_from_legacy_messages", fake_complete_from_legacy_messages)

    text, tool_calls = await svc.chat_completion_with_tools(
        model="gpt-4o",
        system_prompt="You are a helpful agent.",
        messages=[{"role": "user", "content": "Hello"}],
        tools=[],
    )

    assert len(facade_calls) == 1
    assert facade_calls[0]["provider"] == "openai"
    assert facade_calls[0]["model"] == "gpt-4o"
    assert text == "Hello from OpenAI"
    assert tool_calls == []


@pytest.mark.asyncio
async def test_chat_completion_routes_o_series_through_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """o-series OpenAI models (o1, o3, o4-mini) must route through facade."""
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "openai_api_key", "sk-oai-test")
    monkeypatch.setattr(config.settings, "llm_use_legacy_http", False)

    facade_calls: list[dict] = []

    from backend.llm.contracts import LLMResponse

    async def fake_complete_from_legacy_messages(**kwargs):
        facade_calls.append(kwargs)
        return LLMResponse(
            text="Hello from o3",
            tool_calls=[],
            provider="openai",
            model=kwargs["model"],
            request_id="req-o3",
        )

    svc = LLMService()
    monkeypatch.setattr(svc._facade, "complete_from_legacy_messages", fake_complete_from_legacy_messages)

    for model in ("o1", "o3", "o4-mini", "o1-mini"):
        facade_calls.clear()
        await svc.chat_completion_with_tools(
            model=model,
            system_prompt="You are a helpful agent.",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
        )
        assert len(facade_calls) == 1, f"model={model!r} did not call facade"
        assert facade_calls[0]["provider"] == "openai", f"model={model!r} did not route to openai"
