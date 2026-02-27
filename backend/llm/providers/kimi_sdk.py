from __future__ import annotations

from openai import AsyncOpenAI

from backend.llm.providers.openai_sdk import OpenAISDKProvider


class KimiSDKProvider(OpenAISDKProvider):
    """Moonshot / Kimi provider — OpenAI-compatible API with a custom base URL."""

    name = "kimi"

    def __init__(self, api_key: str, base_url: str = "https://api.moonshot.cn/v1"):
        # Bypass parent __init__ and build the client directly with base_url
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
