from __future__ import annotations

from typing import Any

import httpx

from backend.llm.contracts import LLMProviderError, LLMRequest, LLMResponse, LLMToolCall
from backend.llm.providers.base import BaseLLMProvider
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


class GeminiProviderAdapter(BaseLLMProvider):
    """
    Gemini provider adapter.

    Uses the existing HTTP interface shape, but behind the shared provider contract.
    """

    name = "google"

    def __init__(self, api_key: str, timeout_seconds: int = 60):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        declarations = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            }
            for t in request.tools
        ]

        contents: list[dict[str, Any]] = []
        issued_function_names_by_id: dict[str, str] = {}
        for msg in request.messages:
            if msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content or ""}]})
            elif msg.role == "assistant":
                parts: list[dict[str, Any]] = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    if not tc.name:
                        logger.warning("Skipping malformed functionCall with empty name: %s", tc)
                        continue
                    function_call: dict[str, Any] = {
                        "name": tc.name,
                        "args": tc.input or {},
                    }
                    if tc.id:
                        function_call["id"] = tc.id
                        issued_function_names_by_id[tc.id] = tc.name
                    parts.append(
                        {
                            "functionCall": function_call
                        }
                    )
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif msg.role == "tool":
                tool_use_id = msg.tool_use_id or ""
                function_name = issued_function_names_by_id.get(tool_use_id, "")
                if not function_name:
                    logger.warning(
                        "Skipping orphan functionResponse with unknown tool_use_id=%r",
                        tool_use_id,
                    )
                    continue
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    **({"id": tool_use_id} if tool_use_id else {}),
                                    "name": function_name,
                                    "response": {"result": str(msg.content or "")},
                                }
                            }
                        ],
                    }
                )

        if not contents:
            # Avoid 400 when all prior messages are filtered out (e.g., orphan tool results only).
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": request.system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]

        model_name = request.model
        if model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:"
            f"generateContent?key={self.api_key}"
        )

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise LLMProviderError(
                    f"Gemini request failed with status {resp.status_code}",
                    provider=self.name,
                    status_code=resp.status_code,
                    body=resp.text[:1000],
                )
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMProviderError("Gemini response did not include candidates", provider=self.name)
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        parts = (first.get("content") or {}).get("parts") or []

        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text_parts.append(str(part.get("text", "")))
            fc = part.get("functionCall")
            if isinstance(fc, dict):
                tool_calls.append(
                    LLMToolCall(
                        id=str(fc.get("id", "")),
                        name=str(fc.get("name", "")),
                        input=fc.get("args") if isinstance(fc.get("args"), dict) else {},
                    )
                )

        return LLMResponse(
            text="\n".join(p for p in text_parts if p).strip(),
            tool_calls=tool_calls,
            provider=self.name,
            model=request.model,
            request_id=None,
            raw=data,
        )

