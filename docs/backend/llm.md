# LLM Layer

The LLM layer (`backend/llm/`) provides a provider-agnostic interface for making LLM calls. It sits between the inner loop / orchestrator and the actual cloud LLM APIs.

## Module Overview

```
backend/llm/
├── contracts.py          # Shared data contracts (LLMRequest, LLMResponse, etc.)
├── router.py             # Provider selection by model name
├── model_resolver.py     # Role + seniority → model string resolution
├── cloud_facade.py       # Optional high-level façade
├── tool_name_adapter.py  # Tool name normalization across providers
├── providers/
│   ├── base.py           # Abstract base class
│   ├── anthropic_sdk.py  # Anthropic Claude (via anthropic Python SDK)
│   ├── gemini_sdk.py     # Google Gemini (via google-generativeai SDK)
│   └── openai_sdk.py     # OpenAI GPT (via openai Python SDK)
└── __init__.py
```

---

## Contracts

All LLM interaction is expressed in provider-independent dataclasses defined in `backend/llm/contracts.py`.

### LLMTool

Describes a tool available to the model.

```python
@dataclass(slots=True)
class LLMTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
```

The `input_schema` follows JSON Schema format. Providers translate this to their native format (Anthropic `input_schema`, Google function declaration, OpenAI function parameters).

### LLMToolCall

A tool invocation returned by the model.

```python
@dataclass(slots=True)
class LLMToolCall:
    id: str           # Provider-generated unique ID for this call
    name: str         # Tool name
    input: dict[str, Any]   # Tool arguments
```

### LLMMessage

A message in the conversation history.

```python
@dataclass(slots=True)
class LLMMessage:
    role: MessageRole       # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    tool_use_id: str = ""   # For tool-role messages: the call ID being responded to
```

### LLMRequest

Complete request payload.

```python
@dataclass(slots=True)
class LLMRequest:
    model: str
    system_prompt: str
    messages: list[LLMMessage]
    tools: list[LLMTool] = field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int = 1024
    provider: str | None = None   # Optional explicit provider override
```

The `provider` field overrides model-name-based detection when set.

### LLMResponse

Normalized response from any provider.

```python
@dataclass(slots=True)
class LLMResponse:
    text: str                         # Text content (may be empty if only tool calls)
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    request_id: str | None = None     # Provider trace ID
    raw: Any = None                   # Original provider response object
```

### LLMProviderError

Raised when a provider returns an error.

```python
class LLMProviderError(RuntimeError):
    provider: str
    status_code: int | None
    request_id: str | None
    body: str | None
```

---

## Provider Router

`ProviderRouter` (`backend/llm/router.py`) selects the correct provider implementation based on the model name string. It uses keyword matching:

| Keywords in model name | → Provider |
|------------------------|-----------|
| `claude`, `anthropic` | Anthropic |
| `gemini`, `google` | Google |
| `gpt`, `chatgpt`, `openai`, `o1`, `o2`, `o3`, `o4...` | OpenAI |

OpenAI o-series models are matched by a regex: `^o\d` (starts with `o` followed by a digit).

If no keyword matches, the router falls back to whichever API key is configured (`CLAUDE_API_KEY` → Anthropic, `GEMINI_API_KEY` → Google, `OPENAI_API_KEY` → OpenAI). If none are configured, raises `RuntimeError`.

An optional `provider` field in `LLMRequest` can override detection, accepting `"anthropic"`, `"google"`, or `"openai"`.

### `get_provider(model, provider=None) → BaseLLMProvider`

Returns an instantiated provider. Each call creates a new provider instance (they are stateless wrappers). Provider constructors require the relevant API key from `settings`.

---

## Model Resolver

`backend/llm/model_resolver.py` maps agent role and seniority to a model string, consulting `settings` for defaults.

### Engineer seniority tiers

Engineers have three seniority levels, each with a configurable default model:

| Tier | Setting |
|------|---------|
| `junior` | `settings.engineer_junior_model` |
| `intermediate` | `settings.engineer_intermediate_model` |
| `senior` | `settings.engineer_senior_model` |

The `tier` field is stored on `agents.tier` (added in migration 008).

### `resolve_model(role, seniority=None, model_override=None) → str`

Decision order:
1. If role is `engineer`: use `_engineer_model_for_seniority(seniority)`
2. If `model_override` is set and non-empty: use it
3. Otherwise: use `default_model_for_role(role)` from settings

**Default models by role:**
- `manager` → `settings.manager_model_default`
- `cto` → `settings.cto_model_default`
- `engineer` → seniority-based (above)

The `model_override` field on the `agents` DB row allows per-agent model customization. For engineers, the `tier` field drives the default model; `model_override` (if set) takes precedence over tier defaults.

---

## Provider Implementations

### BaseLLMProvider

```python
class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
```

All providers implement the single `complete()` method. The inner loop calls `LLMService.chat_completion_with_tools()` which translates the `PromptAssembly` state into an `LLMRequest` and delegates to the provider.

### AnthropicSDKProvider

Uses the official `anthropic` Python SDK. Translates `LLMRequest` into Anthropic's `messages.create()` call:
- `system_prompt` → Anthropic `system` parameter
- `messages` → translated role-by-role, with tool_use/tool_result blocks for tool interactions
- `tools` → Anthropic `tools` list with `input_schema`
- Returns `LLMResponse` with text extracted from content blocks and tool calls extracted from `tool_use` blocks

Anthropic-specific behavior:
- Tool calls arrive as `content` blocks with `type="tool_use"`
- Tool results must be sent as `user`-role messages with `type="tool_result"` blocks
- Tool call IDs are Anthropic-generated strings (e.g., `toolu_01XY...`)

### GeminiProviderAdapter

Uses the `google-generativeai` SDK. Translates to Gemini's function calling format:
- Tools become `FunctionDeclaration` objects
- Tool calls arrive as `function_call` parts in the response
- Tool results are sent as `function_response` parts in the next user turn

The adapter handles Gemini's different content structure (parts-based) and maps it to the common `LLMResponse` format.

### OpenAISDKProvider

Uses the `openai` Python SDK. Translates to OpenAI's chat completions format:
- Tools become `function` or `tool` objects in the `tools` parameter
- Tool calls arrive in `message.tool_calls` list
- Tool results are sent as `tool` role messages with `tool_call_id`

---

## Tool Name Adapter

`backend/llm/tool_name_adapter.py` normalizes tool names between what the agent loop uses and what different providers accept. Some providers have constraints on tool name characters (e.g., no spaces). This module applies and reverses normalization so tools are always identified by their canonical name in the loop.

---

## LLM Service

`backend/services/llm_service.py` is the thin service used by the inner loop. It:
1. Takes model, system_prompt, messages (as dicts from `PromptAssembly`), and tools (as dicts)
2. Converts them to `LLMRequest` using the appropriate contracts
3. Calls `ProviderRouter.get_provider(model).complete(request)`
4. Returns `(text: str, tool_calls: list[dict])` — the format expected by `loop.py`

The service is instantiated once per session in the inner loop (stateless, no DB dependency).

---

## Configuration

All LLM configuration is read from `backend/config.py` (pydantic-settings, env-based):

| Setting | Env Var | Description |
|---------|---------|-------------|
| Anthropic API key | `CLAUDE_API_KEY` | Required for Anthropic provider |
| Google API key | `GEMINI_API_KEY` | Required for Google provider |
| OpenAI API key | `OPENAI_API_KEY` | Required for OpenAI provider |
| Manager model | `MANAGER_MODEL_DEFAULT` | Default model for Manager agents |
| CTO model | `CTO_MODEL_DEFAULT` | Default model for CTO agents |
| Engineer junior model | `ENGINEER_JUNIOR_MODEL` | Default for junior engineers |
| Engineer intermediate model | `ENGINEER_INTERMEDIATE_MODEL` | Default for intermediate engineers |
| Engineer senior model | `ENGINEER_SENIOR_MODEL` | Default for senior engineers |
| LLM timeout | `LLM_REQUEST_TIMEOUT_SECONDS` | Per-request timeout (default: 60s) |
| Max tokens | `LLM_MAX_TOKENS` | Max tokens per response (default: 1024) |
| Temperature | `LLM_TEMPERATURE` | Sampling temperature (default: 0.2) |

---

## Adding a New Provider

1. Create `backend/llm/providers/my_provider.py` implementing `BaseLLMProvider`
2. Add keyword detection in `ProviderRouter.resolve_provider_name()` 
3. Add instantiation in `ProviderRouter.get_provider()`
4. Add the provider's API key to `Settings` in `backend/config.py`
5. Write tests in `backend/tests/llm/test_my_provider.py`

The inner loop and orchestrator require zero changes — they call `LLMService`, which calls `ProviderRouter`, which calls the provider.
