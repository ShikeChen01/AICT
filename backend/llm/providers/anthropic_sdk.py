from __future__ import annotations

import base64
from typing import Any

from anthropic import APIStatusError, AsyncAnthropic

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


class AnthropicSDKProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        api_messages, issued_ids = self._build_messages(request.messages)
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system_prompt,
            "messages": api_messages,
        }
        if request.tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in request.tools
            ]

        try:
            resp = await self.client.messages.create(**payload)
        except APIStatusError as exc:
            body = ""
            try:
                body = str(exc.response.json())
            except Exception:
                body = str(exc)
            raise LLMProviderError(
                f"Anthropic request failed: {exc}",
                provider=self.name,
                status_code=getattr(exc, "status_code", None),
                request_id=getattr(exc, "request_id", None),
                body=body[:1000],
            ) from exc

        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for block in resp.content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    text_parts.append(text)
            elif block_type == "tool_use":
                tc_id = getattr(block, "id", "")
                tc_name = getattr(block, "name", "")
                tc_input = getattr(block, "input", {}) or {}
                if tc_id and tc_name:
                    tool_calls.append(
                        LLMToolCall(
                            id=tc_id,
                            name=tc_name,
                            input=tc_input if isinstance(tc_input, dict) else {},
                        )
                    )

        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text="\n".join(p for p in text_parts if p).strip(),
            tool_calls=tool_calls,
            provider=self.name,
            model=request.model,
            request_id=getattr(resp, "_request_id", None),
            raw=resp,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )

    def _build_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[list[dict[str, Any]], set[str]]:
        api_messages: list[dict[str, Any]] = []
        issued_tool_use_ids: set[str] = set()
        resolved_tool_use_ids: set[str] = set()
        for msg in messages:
            if msg.role == "user":
                content_blocks: list[dict[str, Any]] = []
                # Images must come before the text block per Anthropic's spec.
                for img in msg.image_parts:
                    b64 = base64.b64encode(img.data).decode()
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.media_type,
                            "data": b64,
                        },
                    })
                text = (msg.content or "").strip() or "\u200b"
                content_blocks.append({"type": "text", "text": text})
                api_messages.append({"role": "user", "content": content_blocks})
                continue

            if msg.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    if not tc.id or not tc.name:
                        logger.warning("Skipping malformed tool_call in assistant message: %s", tc)
                        continue
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.input or {},
                        }
                    )
                    issued_tool_use_ids.add(tc.id)
                if not blocks:
                    blocks.append({"type": "text", "text": "\u200b"})
                api_messages.append({"role": "assistant", "content": blocks})
                continue

            if msg.role == "tool":
                tool_use_id = msg.tool_use_id or ""
                if not tool_use_id or tool_use_id not in issued_tool_use_ids:
                    logger.warning(
                        "Skipping orphan tool_result with unknown tool_use_id=%r",
                        tool_use_id,
                    )
                    continue
                resolved_tool_use_ids.add(tool_use_id)
                # Anthropic tool_result supports multimodal content blocks
                tool_content: list[dict[str, Any]] = []
                for img in msg.image_parts:
                    b64 = base64.b64encode(img.data).decode()
                    tool_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.media_type,
                            "data": b64,
                        },
                    })
                tool_content.append({"type": "text", "text": str(msg.content or "") or "\u200b"})
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": tool_content,
                            }
                        ],
                    }
                )

        dangling = issued_tool_use_ids - resolved_tool_use_ids
        if dangling:
            logger.warning(
                "Stripping %d dangling tool_use id(s) with no tool_result: %s",
                len(dangling),
                dangling,
            )
            for am in api_messages:
                if am.get("role") != "assistant":
                    continue
                blocks = am.get("content", [])
                am["content"] = [
                    b for b in blocks
                    if b.get("type") != "tool_use" or b.get("id") not in dangling
                ]
                if not am["content"]:
                    am["content"] = [{"type": "text", "text": "\u200b"}]

        # Anthropic requires the conversation to end with a user-role message.
        # Stripping dangling tool_use blocks or orphaned tool_results can leave an
        # assistant message last, which triggers a 400 "does not support assistant
        # message prefill" error. Guard against this here rather than at every call site.
        if api_messages and api_messages[-1].get("role") == "assistant":
            logger.warning(
                "Last message after build is 'assistant' — appending sentinel user turn "
                "to satisfy Anthropic's conversation-must-end-with-user constraint."
            )
            api_messages.append({"role": "user", "content": [{"type": "text", "text": "\u200b"}]})

        return api_messages, issued_tool_use_ids

