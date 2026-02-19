from __future__ import annotations

from backend.config import settings
from backend.llm.providers.anthropic_sdk import AnthropicSDKProvider
from backend.llm.providers.base import BaseLLMProvider
from backend.llm.providers.gemini_sdk import GeminiProviderAdapter


class ProviderRouter:
    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def resolve_provider_name(self, model: str, provider: str | None = None) -> str:
        if provider:
            normalized = provider.lower()
            if normalized in {"anthropic", "google"}:
                return normalized

        normalized_model = (model or "").lower()
        if "claude" in normalized_model or "anthropic" in normalized_model:
            return "anthropic"
        if "gemini" in normalized_model or "google" in normalized_model:
            return "google"

        if settings.claude_api_key:
            return "anthropic"
        if settings.gemini_api_key:
            return "google"
        return "none"

    def get_provider(self, model: str, provider: str | None = None) -> BaseLLMProvider:
        selected = self.resolve_provider_name(model, provider)
        if selected == "anthropic":
            if not settings.claude_api_key:
                raise RuntimeError("CLAUDE_API_KEY is not configured")
            return AnthropicSDKProvider(api_key=settings.claude_api_key)
        if selected == "google":
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            return GeminiProviderAdapter(
                api_key=settings.gemini_api_key,
                timeout_seconds=self.timeout_seconds,
            )
        raise RuntimeError("No LLM provider configured. Set CLAUDE_API_KEY or GEMINI_API_KEY.")

