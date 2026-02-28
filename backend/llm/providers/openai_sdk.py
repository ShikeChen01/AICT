from __future__ import annotations

import base64
import json
import re
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

# o-series reasoning models: o1, o1-mini, o1-preview, o3, o3-mini, o3-pro, o4-mini, etc.
# These models have restrictions: no temperature support, use developer role, max_completion_tokens.
_O_SERIES_RE = re.compile(r"^o\d", re.IGNORECASE)
_GPT5_SERIES_RE = re.compile(r"^gpt-5(\.|-|$)", re.IGNORECASE)


def _is_o_series(model: str) -> bool:
    return bool(_O_SERIES_RE.match(model.strip()))


def _requires_max_completion_tokens(model: str) -> bool:
    normalized = model.strip()
    return bool(_O_SERIES_RE.match(normalized) or _GPT5_SERIES_RE.match(normalized))


class OpenAISDKProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        o_series = _is_o_series(request.model)
        requires_max_completion_tokens = _requires_max_completion_tokens(request.model)
        messages = self._build_messages(request.system_prompt, request.messages, o_series=o_series)

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
        }

        # o-series reasoning models do not support temperature; omit it entirely.
        # Standard models use temperature normally.
        if not o_series:
            payload["temperature"] = request.temperature

        # o-series uses max_completion_tokens (includes reasoning tokens in the budget).
        # Standard models use the legacy max_tokens parameter.
        if requires_max_completion_tokens:
            payload["max_completion_tokens"] = request.max_tokens
        else:
            payload["max_tokens"] = request.max_tokens

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

        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text.strip(),
            tool_calls=tool_calls,
            provider=self.name,
            model=request.model,
            request_id=getattr(resp, "_request_id", None),
            raw=resp,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    @staticmethod
    def _build_messages(
        system_prompt: str,
        messages: list[LLMMessage],
        *,
        o_series: bool = False,
    ) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        if system_prompt:
            # o-series reasoning models require the "developer" role instead of "system".
            # o1-mini / o1-preview don't support system messages at all, but "developer"
            # is accepted by all current o-series models, so we use it uniformly.
            role = "developer" if o_series else "system"
            api_messages.append({"role": role, "content": system_prompt})

        for msg in messages:
            if msg.role == "user":
                if msg.image_parts:
                    # Multimodal: text + base64-encoded images via data URLs.
                    parts: list[dict[str, Any]] = [{"type": "text", "text": msg.content or ""}]
                    for img in msg.image_parts:
                        b64 = base64.b64encode(img.data).decode()
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{img.media_type};base64,{b64}"},
                        })
                    api_messages.append({"role": "user", "content": parts})
                else:
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
                                "arguments": json.dumps(tc.input or {}),
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
