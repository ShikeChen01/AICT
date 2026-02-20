from __future__ import annotations

import re

from backend.config import settings
from backend.llm.providers.anthropic_sdk import AnthropicSDKProvider
from backend.llm.providers.base import BaseLLMProvider
from backend.llm.providers.gemini_sdk import GeminiProviderAdapter
from backend.llm.providers.openai_sdk import OpenAISDKProvider
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# Matches OpenAI o-series models: o1, o3, o4-mini, o1-mini, o3-pro, etc.
_OPENAI_O_SERIES_RE = re.compile(r"^o\d")


class ProviderRouter:
    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def resolve_provider_name(self, model: str, provider: str | None = None) -> str:
        if provider:
            normalized = provider.lower()
            if normalized in {"anthropic", "google", "openai"}:
                return normalized

        normalized_model = (model or "").lower()
        if "claude" in normalized_model or "anthropic" in normalized_model:
            return "anthropic"
        if "gemini" in normalized_model or "google" in normalized_model:
            return "google"
        if (
            "gpt" in normalized_model
            or "chatgpt" in normalized_model
            or "openai" in normalized_model
            or _OPENAI_O_SERIES_RE.match(normalized_model)
        ):
            return "openai"

        # No keyword match — fall back to whichever API key is configured
        if settings.claude_api_key:
            logger.warning(
                "Model %r did not match any known provider; falling back to anthropic", model
            )
            return "anthropic"
        if settings.gemini_api_key:
            logger.warning(
                "Model %r did not match any known provider; falling back to google", model
            )
            return "google"
        if settings.openai_api_key:
            logger.warning(
                "Model %r did not match any known provider; falling back to openai", model
            )
            return "openai"
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
        if selected == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            return OpenAISDKProvider(api_key=settings.openai_api_key)
        raise RuntimeError(
            "No LLM provider configured. Set CLAUDE_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."
        )
