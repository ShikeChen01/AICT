"""
LLM service for manager responses.

Supports Anthropic, Google Gemini, and OpenAI with provider auto-selection.
All providers route through the CloudLLMFacade/ProviderRouter when
``llm_use_legacy_http`` is False (the default). Legacy direct-HTTP paths are
kept for backward compatibility but are not the recommended code path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import httpx

from backend.config import settings
from backend.llm.cloud_facade import CloudLLMFacade
from backend.logging.my_logger import get_logger

# Matches OpenAI o-series models: o1, o3, o4-mini, o1-mini, o3-pro, etc.
_OPENAI_O_SERIES_RE = re.compile(r"^o\d")

logger = get_logger(__name__)


class LLMService:
    """Generate chat completions from configured LLM providers."""

    def __init__(self, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds or settings.llm_request_timeout_seconds
        self._facade = CloudLLMFacade(timeout_seconds=self.timeout_seconds)

    @staticmethod
    def _require_model(model: str) -> str:
        resolved = (model or "").strip()
        if not resolved:
            raise RuntimeError("Model must be resolved before calling LLMService")
        return resolved

    async def generate_gm_response(
        self,
        model: str,
        history: Iterable[Any],
        user_message: str,
        project_context: dict[str, Any] | None = None,
    ) -> str:
        """Generate a manager response from history and the latest user message."""
        model = self._require_model(model)
        provider = self._select_provider(model)
        system_prompt = self._build_system_prompt(project_context or {})
        messages = self._build_messages(history, user_message)

        if provider == "none":
            raise RuntimeError(
                "No LLM provider configured. "
                "Set CLAUDE_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."
            )

        if not settings.llm_use_legacy_http:
            response = await self._facade.complete_from_legacy_messages(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=[],
                provider=provider,
            )
            logger.info(
                "LLM facade response: provider=%s model=%s request_id=%s",
                response.provider,
                response.model,
                response.request_id,
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("LLM response did not contain text content")
            return text

        # Legacy direct-HTTP paths
        if provider == "google":
            return await self._call_google(model, system_prompt, messages)
        if provider == "anthropic":
            return await self._call_anthropic(model, system_prompt, messages)
        raise RuntimeError(
            f"Provider '{provider}' is not supported in legacy HTTP mode. "
            "Set LLM_USE_LEGACY_HTTP=false to use the facade for all providers."
        )

    @staticmethod
    def _select_provider(model: str) -> str:
        normalized = (model or "").lower()
        if "claude" in normalized or "anthropic" in normalized:
            if settings.claude_api_key:
                return "anthropic"
        if "gemini" in normalized or "google" in normalized:
            if settings.gemini_api_key:
                return "google"
        if (
            "gpt" in normalized
            or "chatgpt" in normalized
            or "openai" in normalized
            or _OPENAI_O_SERIES_RE.match(normalized)
        ):
            if settings.openai_api_key:
                return "openai"

        # No keyword match — fall back to whichever API key is configured
        if settings.claude_api_key:
            return "anthropic"
        if settings.gemini_api_key:
            return "google"
        if settings.openai_api_key:
            return "openai"
        return "none"

    @staticmethod
    def _build_messages(history: Iterable[Any], user_message: str) -> list[dict[str, str]]:
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

    @staticmethod
    def _build_system_prompt(project_context: dict[str, Any]) -> str:
        open_tasks = project_context.get("open_tasks", 0)
        pending_messages = project_context.get("pending_messages", 0)
        active_agents = project_context.get("active_agents", 0)

        return (
            "You are the Manager agent for AICT.\n"
            "Respond concisely, with concrete next steps.\n"
            "When useful, mention task planning, agent coordination, and repo actions.\n"
            "Do not fabricate tool outputs. If action requires tools, say what you would do.\n\n"
            f"Project context: open_tasks={open_tasks}, "
            f"pending_messages={pending_messages}, active_agents={active_agents}."
        )

    async def _call_anthropic(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        model = self._require_model(model)
        payload = {
            "model": model,
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": msg["role"],
                    "content": [{"type": "text", "text": msg["content"]}],
                }
                for msg in messages
            ],
        }
        headers = {
            "x-api-key": settings.claude_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content_blocks = data.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise RuntimeError("Anthropic response did not contain text content")
        return text

    async def _call_google(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        model_name = self._require_model(model)
        if model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1]
        contents = [
            {
                "role": "model" if msg["role"] == "assistant" else "user",
                "parts": [{"text": str(msg["content"] or "")}],
            }
            for msg in messages
        ]
        if not contents:
            # Gemini expects at least one contents item.
            contents = [{"role": "user", "parts": [{"text": ""}]}]
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": settings.llm_temperature,
                "maxOutputTokens": settings.llm_max_tokens,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:"
            f"generateContent?key={settings.gemini_api_key}"
        )

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.error(
                    "Gemini generateContent failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:1000],
                )
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not include candidates")

        parts = (
            (candidates[0].get("content") or {}).get("parts")
            if isinstance(candidates[0], dict)
            else None
        ) or []
        text_parts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise RuntimeError("Gemini response did not contain text content")
        return text

    # ── Universal loop: chat with tools (returns content + tool_calls) ──

    async def chat_completion_with_tools(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], Any]:
        """
        Non-streaming chat with tool support. Used by the universal agent loop.
        messages: list of {role, content} or {role, content, tool_calls} / {role, role: "tool", content, tool_use_id}
        tools: list of {name, description, input_schema}
        Returns (content_text, tool_calls, llm_response) where:
          - content_text: str
          - tool_calls: list of {id, name, input}
          - llm_response: LLMResponse (carries input_tokens, output_tokens, provider, model)
        """
        from backend.llm.contracts import LLMResponse as _LLMResponse

        model = self._require_model(model)
        provider = self._select_provider(model)

        if provider == "none":
            raise RuntimeError(
                "No LLM provider configured. "
                "Set CLAUDE_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."
            )

        if not settings.llm_use_legacy_http:
            response = await self._facade.complete_from_legacy_messages(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                provider=provider,
            )
            logger.info(
                "LLM facade response: provider=%s model=%s request_id=%s tool_calls=%d in=%d out=%d",
                response.provider,
                response.model,
                response.request_id,
                len(response.tool_calls),
                response.input_tokens,
                response.output_tokens,
            )
            tool_calls = [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in response.tool_calls
            ]
            return response.text, tool_calls, response

        # Legacy direct-HTTP paths — wrap result in a minimal LLMResponse stub
        if provider == "google":
            text, calls = await self._call_google_with_tools(model, system_prompt, messages, tools)
        elif provider == "anthropic":
            text, calls = await self._call_anthropic_with_tools(model, system_prompt, messages, tools)
        else:
            raise RuntimeError(
                f"Provider '{provider}' is not supported in legacy HTTP mode. "
                "Set LLM_USE_LEGACY_HTTP=false to use the facade for all providers."
            )
        stub = _LLMResponse(text=text, provider=provider, model=model)
        return text, calls, stub

    async def _call_anthropic_with_tools(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Anthropic messages API with tool use."""
        model = self._require_model(model)
        api_messages: list[dict] = []
        issued_tool_use_ids: set[str] = set()
        resolved_tool_use_ids: set[str] = set()
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                api_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": content or ""}],
                })
            elif role == "assistant":
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in m.get("tool_calls", []):
                    tc_id = tc.get("id", "")
                    tc_name = tc.get("name", "")
                    if not tc_id or not tc_name:
                        logger.warning("Skipping malformed tool_call in assistant message: %s", tc)
                        continue
                    blocks.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": tc_name,
                        "input": tc.get("input") or {},
                    })
                    issued_tool_use_ids.add(tc_id)
                if not blocks:
                    blocks.append({"type": "text", "text": ""})
                api_messages.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                tool_use_id = m.get("tool_use_id", "")
                if not tool_use_id or tool_use_id not in issued_tool_use_ids:
                    logger.warning(
                        "Skipping orphan tool_result with unknown tool_use_id=%r",
                        tool_use_id,
                    )
                    continue
                resolved_tool_use_ids.add(tool_use_id)
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": str(m.get("content", "")),
                    }],
                })

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
                    am["content"] = [{"type": "text", "text": ""}]

        # Anthropic tools format
        api_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

        payload = {
            "model": model,
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
            "system": system_prompt,
            "messages": api_messages,
            "tools": api_tools,
        }
        headers = {
            "x-api-key": settings.claude_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error(
                    "Anthropic /v1/messages failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:1000],
                )
            resp.raise_for_status()
            data = resp.json()

        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input") or {},
                })
        text = "\n".join(p for p in text_parts if p).strip()
        return text, tool_calls

    async def _call_google_with_tools(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Gemini with function calling. Returns (text, tool_calls)."""
        model = self._require_model(model)
        # Gemini function declarations
        declarations = [
            {
                "name": str(t["name"]),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            }
            for t in tools
            if isinstance(t, dict) and t.get("name")
        ]
        # Build contents (role + parts); tool results as function_response
        contents = []
        issued_function_names_by_id: dict[str, str] = {}
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content or ""}],
                })
            elif role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                for tc in m.get("tool_calls", []):
                    if not isinstance(tc, dict):
                        continue
                    function_name = str(tc.get("name", "") or "")
                    if not function_name:
                        logger.warning("Skipping malformed functionCall with empty name: %s", tc)
                        continue
                    function_call = {
                        "name": function_name,
                        "args": tc.get("input") if isinstance(tc.get("input"), dict) else {},
                    }
                    tc_id = tc.get("id", "")
                    if tc_id:
                        function_call["id"] = tc_id
                        issued_function_names_by_id[tc_id] = function_name
                    parts.append({
                        "functionCall": function_call
                    })
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                tool_use_id = m.get("tool_use_id", "")
                function_name = issued_function_names_by_id.get(tool_use_id, "")
                if not function_name:
                    logger.warning(
                        "Skipping orphan functionResponse with unknown tool_use_id=%r",
                        tool_use_id,
                    )
                    continue
                parts = [{
                    "functionResponse": {
                        **({"id": tool_use_id} if tool_use_id else {}),
                        "name": function_name,
                        "response": {"result": str(m.get("content", ""))},
                    }
                }]
                contents.append({"role": "user", "parts": parts})

        if not contents:
            # Avoid 400 when all prior messages were filtered out.
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        model_name = model
        if model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:"
            f"generateContent?key={settings.gemini_api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": settings.llm_temperature,
                "maxOutputTokens": settings.llm_max_tokens,
            },
        }
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.error(
                    "Gemini generateContent failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:1000],
                )
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not include candidates")
        c = candidates[0]
        parts = (c.get("content") or {}).get("parts") or []
        text_parts = []
        tool_calls = []
        for part in parts:
            if isinstance(part, dict):
                if "text" in part:
                    text_parts.append(part.get("text", ""))
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append({
                        "id": fc.get("id", ""),
                        "name": fc.get("name", ""),
                        "input": fc.get("args") or {},
                    })
        text = "\n".join(p for p in text_parts if p).strip()
        return text, tool_calls

