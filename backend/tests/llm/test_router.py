import pytest

from backend.llm.router import ProviderRouter


def test_resolve_provider_from_model_name() -> None:
    router = ProviderRouter()
    assert router.resolve_provider_name("claude-opus-4-5-20251101") == "anthropic"
    assert router.resolve_provider_name("gemini-2.0-flash") == "google"
    assert router.resolve_provider_name("gpt-5-mini") == "openai"
    assert router.resolve_provider_name("o3-deep-research") == "openai"


def test_resolve_provider_prefers_explicit_provider() -> None:
    router = ProviderRouter()
    assert router.resolve_provider_name("gemini-2.0-flash", provider="anthropic") == "anthropic"
    assert router.resolve_provider_name("claude-sonnet-4-6", provider="openai") == "openai"


def test_get_provider_raises_when_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import config

    monkeypatch.setattr(config.settings, "claude_api_key", "")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "openai_api_key", "")
    router = ProviderRouter()
    with pytest.raises(RuntimeError, match="No LLM provider configured"):
        router.get_provider("unknown-model")

