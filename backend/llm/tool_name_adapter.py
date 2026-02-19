from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.llm.contracts import LLMMessage, LLMRequest, LLMResponse, LLMTool, LLMToolCall

_MAX_TOOL_NAME_LEN = 128
_INVALID_TOOL_CHARS = re.compile(r"[^a-zA-Z0-9_-]+")
_MULTI_UNDERSCORE = re.compile(r"_+")


def sanitize_tool_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        raw = "tool"
    normalized = _INVALID_TOOL_CHARS.sub("_", raw)
    normalized = _MULTI_UNDERSCORE.sub("_", normalized).strip("_-")
    if not normalized:
        normalized = "tool"
    if len(normalized) > _MAX_TOOL_NAME_LEN:
        normalized = normalized[:_MAX_TOOL_NAME_LEN].rstrip("_-")
    return normalized or "tool"


def _with_suffix(base: str, suffix: int) -> str:
    suffix_str = f"_{suffix}"
    available = _MAX_TOOL_NAME_LEN - len(suffix_str)
    stem = base[:available].rstrip("_-") or "tool"
    return f"{stem}{suffix_str}"


@dataclass(slots=True)
class ToolNameAdapter:
    to_canonical_map: dict[str, str] = field(default_factory=dict)
    to_original_map: dict[str, str] = field(default_factory=dict)

    def to_canonical(self, original_name: str) -> str:
        original = str(original_name or "")
        if original in self.to_canonical_map:
            return self.to_canonical_map[original]

        candidate = sanitize_tool_name(original)
        if candidate in self.to_original_map and self.to_original_map[candidate] != original:
            suffix = 2
            while True:
                disambiguated = _with_suffix(candidate, suffix)
                if (
                    disambiguated not in self.to_original_map
                    or self.to_original_map[disambiguated] == original
                ):
                    candidate = disambiguated
                    break
                suffix += 1

        self.to_canonical_map[original] = candidate
        self.to_original_map[candidate] = original
        return candidate

    def to_original(self, canonical_name: str) -> str:
        canonical = str(canonical_name or "")
        return self.to_original_map.get(canonical, canonical)


def normalize_request_tool_names(request: LLMRequest) -> tuple[LLMRequest, ToolNameAdapter | None]:
    adapter = ToolNameAdapter()
    saw_tool_names = False

    normalized_tools: list[LLMTool] = []
    for t in request.tools:
        canonical = adapter.to_canonical(t.name)
        saw_tool_names = True
        normalized_tools.append(
            LLMTool(
                name=canonical,
                description=t.description,
                input_schema=t.input_schema,
            )
        )

    normalized_messages: list[LLMMessage] = []
    for msg in request.messages:
        if not msg.tool_calls:
            normalized_messages.append(msg)
            continue

        normalized_calls: list[LLMToolCall] = []
        for tc in msg.tool_calls:
            canonical = adapter.to_canonical(tc.name)
            saw_tool_names = True
            normalized_calls.append(
                LLMToolCall(
                    id=tc.id,
                    name=canonical,
                    input=tc.input,
                )
            )
        normalized_messages.append(
            LLMMessage(
                role=msg.role,
                content=msg.content,
                tool_calls=normalized_calls,
                tool_use_id=msg.tool_use_id,
            )
        )

    if not saw_tool_names:
        return request, None

    normalized_request = LLMRequest(
        model=request.model,
        system_prompt=request.system_prompt,
        messages=normalized_messages,
        tools=normalized_tools,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        provider=request.provider,
    )
    return normalized_request, adapter


def denormalize_response_tool_calls(response: LLMResponse, adapter: ToolNameAdapter) -> LLMResponse:
    if not response.tool_calls:
        return response
    denormalized_calls = [
        LLMToolCall(id=tc.id, name=adapter.to_original(tc.name), input=tc.input)
        for tc in response.tool_calls
    ]
    return LLMResponse(
        text=response.text,
        tool_calls=denormalized_calls,
        provider=response.provider,
        model=response.model,
        request_id=response.request_id,
        raw=response.raw,
    )
