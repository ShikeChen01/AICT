"""Factory for chat model adapters routed through CloudLLMFacade."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from backend.llm.cloud_facade import CloudLLMFacade
from backend.llm.model_resolver import default_model_for_role


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p).strip()
    return str(content or "")


def _tool_schema(tool: Any) -> dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        schema = args_schema.model_json_schema()
        if isinstance(schema, dict):
            return schema
    args = getattr(tool, "args", None)
    if isinstance(args, dict):
        return {"type": "object", "properties": args}
    return {"type": "object", "properties": {}}


def _default_model_for_role(role: str | None) -> str:
    return default_model_for_role(role)


class CloudChatModelAdapter:
    def __init__(
        self,
        *,
        model_name: str,
        bound_tools: list[dict[str, Any]] | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.bound_tools = bound_tools or []
        self.facade = CloudLLMFacade(timeout_seconds=timeout_seconds)

    def bind_tools(self, tools: list[Any]) -> "CloudChatModelAdapter":
        normalized_tools = [
            {
                "name": str(getattr(tool, "name", "")),
                "description": str(getattr(tool, "description", "")),
                "input_schema": _tool_schema(tool),
            }
            for tool in tools
            if getattr(tool, "name", None)
        ]
        return CloudChatModelAdapter(
            model_name=self.model_name,
            bound_tools=normalized_tools,
            timeout_seconds=self.facade.timeout_seconds,
        )

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        system_blocks: list[str] = []
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_blocks.append(_text_from_content(msg.content))
            elif isinstance(msg, HumanMessage):
                api_messages.append({"role": "user", "content": _text_from_content(msg.content)})
            elif isinstance(msg, AIMessage):
                tool_calls = [
                    {
                        "id": str(tc.get("id", "")),
                        "name": str(tc.get("name", "")),
                        "input": tc.get("args") if isinstance(tc.get("args"), dict) else {},
                    }
                    for tc in (msg.tool_calls or [])
                    if isinstance(tc, dict)
                ]
                api_messages.append(
                    {
                        "role": "assistant",
                        "content": _text_from_content(msg.content),
                        "tool_calls": tool_calls,
                    }
                )
            elif isinstance(msg, ToolMessage):
                api_messages.append(
                    {
                        "role": "tool",
                        "content": _text_from_content(msg.content),
                        "tool_use_id": str(msg.tool_call_id or ""),
                    }
                )

        response = await self.facade.complete_from_legacy_messages(
            model=self.model_name,
            system_prompt="\n\n".join(s for s in system_blocks if s).strip(),
            messages=api_messages,
            tools=self.bound_tools,
        )
        return AIMessage(
            content=response.text or "",
            tool_calls=[
                {
                    "name": tc.name,
                    "args": tc.input,
                    "id": tc.id,
                    "type": "tool_call",
                }
                for tc in response.tool_calls
            ],
        )


def get_model(model_name: str | None = None, role: str | None = None) -> CloudChatModelAdapter:
    resolved = model_name or _default_model_for_role(role)
    return CloudChatModelAdapter(model_name=resolved)
