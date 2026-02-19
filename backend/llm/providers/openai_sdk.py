from __future__ import annotations

from typing import Any

from openai import APIStatusError, AsyncOpenAI

from backend.llm.contracts import (
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
)
from backend.llm.providers.base import BaseLLMProvider
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


class OpenAISDKProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = self._build_messages(request.system_prompt, request.messages)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in request.tools
            ]

        try:
            resp = await self.client.chat.completions.create(**payload)
        except APIStatusError as exc:
            body = ""
            try:
                body = str(exc.response.json())
            except Exception:
                body = str(exc)
            raise LLMProviderError(
                f"OpenAI request failed: {exc}",
                provider=self.name,
                status_code=getattr(exc, "status_code", None),
                request_id=getattr(exc, "request_id", None),
                body=body[:1000],
            ) from exc

        choice = resp.choices[0] if resp.choices else None
        if choice is None:
            raise LLMProviderError(
                "OpenAI response contained no choices",
                provider=self.name,
            )

        message = choice.message
        text = message.content or ""
        tool_calls: list[LLMToolCall] = []

        if message.tool_calls:
            import json

            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    LLMToolCall(
                        id=tc.id or "",
                        name=tc.function.name or "",
                        input=args if isinstance(args, dict) else {},
                    )
                )

        return LLMResponse(
            text=text.strip(),
            tool_calls=tool_calls,
            provider=self.name,
            model=request.model,
            request_id=getattr(resp, "_request_id", None),
            raw=resp,
        )

    @staticmethod
    def _build_messages(
        system_prompt: str, messages: list[LLMMessage]
    ) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content or ""})
            elif msg.role == "assistant":
                entry: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": __import__("json").dumps(tc.input or {}),
                            },
                        }
                        for tc in msg.tool_calls
                        if tc.id and tc.name
                    ]
                if "content" not in entry and "tool_calls" not in entry:
                    entry["content"] = ""
                api_messages.append(entry)
            elif msg.role == "tool":
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_use_id or "",
                        "content": str(msg.content or ""),
                    }
                )

        return api_messages
