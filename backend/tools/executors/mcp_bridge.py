"""MCP bridge executor — proxy tool calls to remote MCP servers via SSE.

Each MCP tool discovered from a connected server is flattened into the agent's
tool registry as a first-class tool. This executor handles the actual call:
    1. Look up the McpServerConfig for the tool.
    2. POST to the server's tools/call endpoint with the tool name and arguments.
    3. Return the text content from the MCP response.

The executor is stateless — it creates a short-lived HTTP connection per call
(connection pooling via a module-level httpx.AsyncClient).

Transport: SSE/HTTP only (MCP Streamable HTTP transport).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from cryptography.fernet import Fernet

from backend.config import settings
from backend.db.models import McpServerConfig
from backend.logging.my_logger import get_logger
from backend.tools.base import RunContext
from backend.tools.result import ToolExecutionError

logger = get_logger(__name__)

# Module-level async client for connection pooling across calls.
_http_client: httpx.AsyncClient | None = None

MCP_CALL_TIMEOUT_S = 30


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=MCP_CALL_TIMEOUT_S)
    return _http_client


def _decrypt_api_key(encrypted: bytes | None) -> str | None:
    """Decrypt a Fernet-encrypted API key, or return None."""
    if not encrypted:
        return None
    try:
        f = Fernet(settings.secret_encryption_key.encode())
        return f.decrypt(encrypted).decode()
    except Exception:
        logger.warning("Failed to decrypt MCP server API key")
        return None


def _build_headers(server: McpServerConfig) -> dict[str, str]:
    """Build HTTP headers for the MCP server request."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = _decrypt_api_key(server.api_key)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # Merge any extra headers stored on the config (values are plain strings).
    if server.headers and isinstance(server.headers, dict):
        for k, v in server.headers.items():
            headers[str(k)] = str(v)
    return headers


# ---------------------------------------------------------------------------
# Discovery: fetch tool definitions from an MCP server
# ---------------------------------------------------------------------------

async def discover_tools(server: McpServerConfig) -> list[dict[str, Any]]:
    """Call tools/list on a remote MCP server and return raw tool definitions.

    Returns a list of dicts with keys: name, description, inputSchema.
    Raises ToolExecutionError on failure.
    """
    url = server.url.rstrip("/")
    headers = _build_headers(server)
    client = _get_client()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }

    try:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
    except httpx.TimeoutException:
        raise ToolExecutionError(
            f"MCP server '{server.name}' timed out during tool discovery.",
            error_code="MCP_TIMEOUT",
            hint="Check that the MCP server URL is reachable.",
        )
    except httpx.HTTPStatusError as exc:
        raise ToolExecutionError(
            f"MCP server '{server.name}' returned HTTP {exc.response.status_code}.",
            error_code="MCP_HTTP_ERROR",
            hint="Verify server URL and authentication credentials.",
        )
    except Exception as exc:
        raise ToolExecutionError(
            f"MCP server '{server.name}' unreachable: {exc}",
            error_code="MCP_CONNECTION_ERROR",
            hint="Check that the MCP server is running and URL is correct.",
        )

    # MCP JSON-RPC response: {"result": {"tools": [...]}}
    result = body.get("result", {})
    tools = result.get("tools", [])
    if not isinstance(tools, list):
        return []
    return tools


def mcp_tool_to_tool_def(
    server: McpServerConfig,
    mcp_tool: dict[str, Any],
) -> dict[str, Any]:
    """Convert an MCP tool definition to our internal tool definition format.

    Prefixes the tool name with the server name to avoid collisions:
        "list_issues" on server "github" → "mcp__github__list_issues"
    """
    raw_name = mcp_tool.get("name", "unknown")
    # Sanitize server name for use as prefix (lowercase, underscores).
    server_prefix = server.name.lower().replace(" ", "_").replace("-", "_")
    prefixed_name = f"mcp__{server_prefix}__{raw_name}"

    input_schema = mcp_tool.get("inputSchema", {"type": "object", "properties": {}})
    # Normalize: MCP uses "inputSchema", our system uses "input_schema"
    if not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}}

    return {
        "name": prefixed_name,
        "description": mcp_tool.get("description", f"MCP tool: {raw_name}"),
        "input_schema": input_schema,
        "allowed_roles": ["*"],
        # Metadata for the bridge executor to route back to the right server.
        "_mcp_server_id": str(server.id),
        "_mcp_raw_tool_name": raw_name,
    }


# ---------------------------------------------------------------------------
# Execution: call a tool on a remote MCP server
# ---------------------------------------------------------------------------

async def run_mcp_tool(ctx: RunContext, tool_input: dict) -> str:
    """Execute an MCP tool call by proxying to the remote server.

    This is the executor function registered for every MCP-sourced tool.
    The tool_input comes directly from the LLM's tool call.

    The server ID and raw tool name are looked up from the ToolConfig row
    associated with this tool (stored as metadata during discovery).
    """
    from sqlalchemy import select
    from backend.db.models import McpServerConfig, ToolConfig

    # The tool name arriving here is the prefixed version (mcp__server__tool).
    # We need to find the corresponding server config and raw tool name.
    tool_name = getattr(ctx, "_current_mcp_tool_name", None)
    if not tool_name:
        raise ToolExecutionError(
            "MCP bridge invoked without tool routing context.",
            error_code="MCP_INTERNAL_ERROR",
        )

    # Look up the ToolConfig to get server_id and raw name.
    result = await ctx.db.execute(
        select(ToolConfig).where(
            ToolConfig.agent_id == ctx.agent.id,
            ToolConfig.tool_name == tool_name,
            ToolConfig.source == "mcp",
        )
    )
    tc = result.scalar_one_or_none()
    if not tc or not tc.mcp_server_id:
        raise ToolExecutionError(
            f"No MCP server mapping found for tool '{tool_name}'.",
            error_code="MCP_NOT_FOUND",
            hint="The MCP server may have been disconnected. Re-sync tools.",
        )

    # Load the server config.
    srv_result = await ctx.db.execute(
        select(McpServerConfig).where(McpServerConfig.id == tc.mcp_server_id)
    )
    server = srv_result.scalar_one_or_none()
    if not server or not server.enabled:
        raise ToolExecutionError(
            f"MCP server '{tc.mcp_server_id}' is disabled or missing.",
            error_code="MCP_SERVER_DISABLED",
            hint="Re-enable the MCP server in the agent's tool configuration.",
        )

    # Extract the raw tool name from the prefixed name.
    raw_tool_name = tool_name.split("__", 2)[-1] if "__" in tool_name else tool_name

    # Build the JSON-RPC request.
    url = server.url.rstrip("/")
    headers = _build_headers(server)
    client = _get_client()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": raw_tool_name,
            "arguments": tool_input,
        },
    }

    try:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
    except httpx.TimeoutException:
        raise ToolExecutionError(
            f"MCP tool '{raw_tool_name}' on '{server.name}' timed out.",
            error_code="MCP_TIMEOUT",
            hint="The MCP server took too long to respond. Try again or check the server.",
        )
    except httpx.HTTPStatusError as exc:
        raise ToolExecutionError(
            f"MCP tool '{raw_tool_name}' on '{server.name}' returned HTTP {exc.response.status_code}.",
            error_code="MCP_HTTP_ERROR",
        )
    except Exception as exc:
        raise ToolExecutionError(
            f"Failed to reach MCP server '{server.name}': {exc}",
            error_code="MCP_CONNECTION_ERROR",
        )

    # Parse MCP JSON-RPC response.
    if "error" in body:
        err = body["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise ToolExecutionError(
            f"MCP server error: {msg}",
            error_code="MCP_SERVER_ERROR",
        )

    result_data = body.get("result", {})

    # MCP tools/call returns {"content": [{"type": "text", "text": "..."}]}
    content_parts = result_data.get("content", [])
    if isinstance(content_parts, list):
        text_parts = [
            p.get("text", "")
            for p in content_parts
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        if text_parts:
            return "\n".join(text_parts)

    # Fallback: JSON-serialize the entire result.
    return json.dumps(result_data, indent=2, default=str)


async def close_client() -> None:
    """Shut down the module-level HTTP client (call during app shutdown)."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
