from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.config import settings
from backend.llm.contracts import ImagePart, LLMMessage, LLMRequest, LLMResponse, LLMTool, LLMToolCall
from backend.llm.router import ProviderRouter
from backend.llm.tool_name_adapter import (
    denormalize_response_tool_calls,
    normalize_request_tool_names,
)


class CloudLLMFacade:
    def __init__(self, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds or settings.llm_request_timeout_seconds
        self.router = ProviderRouter(timeout_seconds=self.timeout_seconds)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        normalized_request, adapter = normalize_request_tool_names(request)
        provider = self.router.get_provider(
            normalized_request.model, normalized_request.provider
        )
        response = await provider.complete(normalized_request)
        if adapter is None:
            return response
        return denormalize_response_tool_calls(response, adapter)

    async def complete_from_legacy_messages(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        provider: str | None = None,
    ) -> LLMResponse:
        canonical_messages: list[LLMMessage] = []
        for msg in messages:
            role = str(msg.get("role", ""))
            if role not in {"user", "assistant", "tool"}:
                continue
            tool_calls = [
                LLMToolCall(
                    id=str(tc.get("id", "")),
                    name=str(tc.get("name", "")),
                    input=tc.get("input") if isinstance(tc.get("input"), dict) else {},
                )
                for tc in msg.get("tool_calls", []) or []
                if isinstance(tc, dict)
            ]
            # Phase 6: image_parts may be stored directly as ImagePart objects in the dict.
            raw_image_parts = msg.get("image_parts") or []
            image_parts = [ip for ip in raw_image_parts if isinstance(ip, ImagePart)]
            canonical_messages.append(
                LLMMessage(
                    role=role,
                    content=str(msg.get("content", "") or ""),
                    tool_calls=tool_calls,
                    tool_use_id=str(msg.get("tool_use_id", "") or ""),
                    image_parts=image_parts,
                )
            )

        canonical_tools = [
            LLMTool(
                name=str(t.get("name", "")),
                description=str(t.get("description", "")),
                input_schema=t.get("input_schema")
                if isinstance(t.get("input_schema"), dict)
                else {"type": "object", "properties": {}},
            )
            for t in tools
            if isinstance(t, dict) and t.get("name")
        ]

        return await self.complete(
            LLMRequest(
                model=model,
                provider=provider,
                system_prompt=system_prompt,
                messages=canonical_messages,
                tools=canonical_tools,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        )

    @staticmethod
    def build_manager_messages(history: Iterable[Any], user_message: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for msg in history:
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "")
            if role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "manager":
                messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages[-40:]

