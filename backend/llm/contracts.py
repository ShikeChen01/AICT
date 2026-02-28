from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


MessageRole = Literal["user", "assistant", "tool"]

# MIME types accepted for image parts across all providers.
SUPPORTED_IMAGE_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})


@dataclass(slots=True)
class ImagePart:
    """A single image included in a multimodal LLM message.

    ``data`` holds raw bytes (loaded from the DB attachment).
    ``media_type`` must be one of the supported image MIME types.
    """

    data: bytes
    media_type: str  # 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp'


@dataclass(slots=True)
class LLMTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass(slots=True)
class LLMToolCall:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMMessage:
    role: MessageRole
    content: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    tool_use_id: str = ""
    # Phase 6: optional multimodal image parts (user messages only)
    image_parts: list[ImagePart] = field(default_factory=list)


@dataclass(slots=True)
class LLMRequest:
    model: str
    system_prompt: str
    messages: list[LLMMessage]
    tools: list[LLMTool] = field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int = 1024
    provider: str | None = None


@dataclass(slots=True)
class LLMResponse:
    text: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    request_id: str | None = None
    raw: Any = None
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        request_id: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
        self.body = body

