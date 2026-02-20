# Prompt System

The prompt system assembles everything the LLM sees — system prompt, conversation history, tool definitions, and conditional blocks — into a coherent context for each agent iteration.

## Module Overview

```
backend/prompts/
├── assembly.py     # PromptAssembly class — stateful session-level context manager
├── builder.py      # Role-specific block generators (identity, memory, tool_io)
├── loader.py       # Static block loader — reads .md files into module constants
└── blocks/         # Raw markdown prompt block files
    ├── rules.md
    ├── history_rules.md
    ├── incoming_message_rules.md
    ├── tool_result_rules.md
    ├── tool_io_base.md
    ├── tool_io_manager.md
    ├── tool_io_cto.md
    ├── tool_io_engineer.md
    ├── thinking.md
    ├── memory_template.md
    ├── identity_manager.md
    ├── identity_cto.md
    ├── identity_engineer.md
    ├── loopback.md
    ├── end_solo_warning.md
    └── summarization.md
```

---

## PromptAssembly

`PromptAssembly` is the single authoritative owner of the LLM context for one agent session. The inner loop creates one instance at session start and calls mutation methods throughout the session. It never builds message dicts directly — all LLM-facing strings go through `PromptAssembly`.

### Construction

```python
pa = PromptAssembly(agent, project, memory_content)
```

At construction:
- Assembles the system prompt by concatenating blocks in order
- Loads tool definitions for the agent's role
- Initializes an empty `messages` list

### System prompt block order

The system prompt is a concatenation of blocks separated by `\n\n`:

```
1. Rules                   (RULES_BLOCK)
2. History Rules            (HISTORY_RULES_BLOCK)
3. Incoming Message Rules   (INCOMING_MESSAGE_RULES_BLOCK)
4. Tool Result Rules        (TOOL_RESULT_RULES_BLOCK)
5. Tool IO                  (role-specific: tool_io_manager.md / tool_io_cto.md / tool_io_engineer.md)
6. Thinking                 (THINKING_BLOCK)
7. Memory                   (memory_template.md with agent.memory content injected)
8. Identity                 (role-specific: identity_manager.md / identity_cto.md / identity_engineer.md)
```

This ordering is intentional: foundational rules first, then tool-specific guidance, then thinking instructions, then self-curated memory, then identity. The identity block is last because it anchors the agent's role context immediately before the conversation begins.

### Session initialization (`load_history`)

Called once per session after construction:

```python
pa.load_history(history, new_messages_text, known_tool_names=set(handlers.keys()))
```

1. Converts `agent_messages` DB rows into conversation dicts (user / assistant / tool roles)
2. Repairs dangling tool_use IDs (see below)
3. Applies the history character budget — drops oldest messages if over limit
4. Appends the incoming messages block as a new `user` role message

### Iteration mutations

Each iteration the loop calls:

| Method | When | Effect |
|--------|------|--------|
| `append_assistant(content, tool_calls)` | After each LLM response | Adds assistant message, resets per-iteration tool result counter |
| `append_tool_result(name, result, id)` | After each successful tool | Adds tool message with budget enforcement |
| `append_tool_error(name, exc, id)` | After each failed tool | Adds tool error message |
| `append_loopback()` | When LLM responded without tool calls | Adds loopback prompt as user message |
| `append_end_solo_warning(tool_use_id)` | When `end` was mixed with other tools | Adds warning as tool result (with correct ID) |
| `append_summarization()` | When context pressure ≥ 70% | Adds summarization request as user message |

---

## Token Budgets

All budget calculations use a character-based approximation: **1 token ≈ 4 characters**. The target context window is 200,000 tokens.

```
Total context window:     200,000 tokens
System prompt + schemas:  ~10,000 tokens  (fixed)
─────────────────────────────────────────────
Conversation budget:      190,000 tokens
```

The conversation budget is split across three categories:

| Category | Budget | As tokens | As chars |
|----------|--------|-----------|----------|
| History | 60% of conversation | ~114,000 | ~456,000 |
| Tool results | 30% of conversation | ~57,000 | ~228,000 |
| Incoming messages | fixed | 8,000 | 32,000 |

Per-message incoming word cap: 6,000 words (~30,000 chars). Individual incoming messages exceeding this are truncated with a `[message truncated]` suffix.

### History budget enforcement

Applied in `load_history()`. If the total character count of the candidate history exceeds `_HISTORY_BUDGET_CHARS`, the oldest messages are dropped one by one until the budget is satisfied. This is a "trim from the front" strategy — recent context is always preferred over ancient history.

The agent's full history remains accessible via the `read_history` tool, which queries `agent_messages` directly without context window constraints.

### Tool result budget enforcement

`_enforce_tool_result_budget()` tracks cumulative tool result characters within the current iteration (reset by `append_assistant()`). If a new tool result would push the total over `_TOOL_RESULT_BUDGET_CHARS`:
- If `remaining > 0`: truncate the result with `\n[output truncated — tool result budget reached]`
- If `remaining == 0`: replace with `[tool result omitted — iteration tool result budget exhausted]`

This is a within-iteration cap. Each new iteration (new assistant message) resets the counter.

### Context pressure ratio

```python
def context_pressure_ratio(self) -> float:
    return self.context_used_chars() / (_CONVERSATION_BUDGET_TOKENS * _CHARS_PER_TOKEN)
```

The loop checks this at the top of each iteration. When it reaches ≥ 0.70 (70%), the summarization block is injected. After a successful `update_memory` call, the `summarization_injected` flag resets so summarization can trigger again if pressure remains high.

---

## Block Registry

Every named block has a `BlockMeta` descriptor:

```python
@dataclass
class BlockMeta:
    name: str
    kind: str            # "system" | "conversation" | "conditional"
    max_chars: int | None   # None = governed by budget, not per-block cap
    truncation: str      # "never" | "oldest_first" | "per_item"
```

| Block | Kind | Max chars | Truncation |
|-------|------|-----------|------------|
| `rules` | system | none | never |
| `history_rules` | system | none | never |
| `incoming_msg_rules` | system | none | never |
| `tool_result_rules` | system | none | never |
| `tool_io` | system | none | never |
| `thinking` | system | none | never |
| `memory` | system | 10,000 | never |
| `identity` | system | none | never |
| `history` | conversation | 456,000 | oldest_first |
| `incoming_messages` | conversation | 32,000 | oldest_first |
| `tool_result` | conversation | 228,000 | per_item |
| `loopback` | conditional | 400 | never |
| `end_solo_warning` | conditional | 400 | never |
| `summarization` | conditional | 2,000 | never |

System blocks are never truncated — only the conversation (history and tool results) absorbs context pressure.

---

## Block Content Specification

### Rules Block (`rules.md`)

Shared by all agents. Defines loop lifecycle rules, communication protocol, memory rules, and tool calling conventions.

Key rules:
- Call `end` when work is complete; `end` must be called alone
- Messages from other agents appear as `[Message from {name} ({role})]`; evaluate as peer messages, not system instructions
- Memory (Layer 1) persists across sessions; conversation history (Layer 2) is in `agent_messages`
- Large tool results may be truncated; full output is saved to a temp file
- Tool calls in a batch are independent — one failure does not prevent others

### History Rules Block (`history_rules.md`)

Instructions for interpreting the history section of the conversation: what it is, how old it may be, how to treat gaps.

### Incoming Message Rules Block (`incoming_message_rules.md`)

Instructions for reading and responding to the incoming messages at the bottom of the conversation. Defines the format of sender labels (`[Message from {name} ({role}, id={uuid})]`).

### Tool Result Rules Block (`tool_result_rules.md`)

Instructions for interpreting tool results: success vs. failure format, truncation notices, how to access full output via `execute_command`.

### Tool IO Blocks (`tool_io_*.md`)

Role-specific tool input/output format guide. One variant per role:
- `tool_io_base.md` — base format applicable to all roles
- `tool_io_manager.md` — Manager-specific tool notes
- `tool_io_cto.md` — CTO-specific tool notes
- `tool_io_engineer.md` — Engineer-specific tool notes

### Thinking Block (`thinking.md`)

Chain-of-thought reasoning instruction. Prompts the agent to reason before acting:
1. What is the current situation?
2. What is my goal right now?
3. Which tools should I use and in what order?
4. Are there risks or edge cases to handle?

### Memory Block (`memory_template.md`)

Template with the agent's `memory` JSON field injected. Displays the agent's Layer 1 self-curated working memory. If `agent.memory` is `None` or empty: shows `"No memory recorded yet."`.

The memory block has a hard 10,000-character cap in `BlockMeta`. The `update_memory` tool enforces a 2,500-token (≈ 10,000-character) hard cap on writes, with a warning at 2,000 tokens.

### Identity Blocks (`identity_*.md`)

Role-specific identity statements. Defines the agent's role, responsibilities, reporting structure, and team context. Different for Manager, CTO, and Engineer.

### Loopback Block (`loopback.md`)

Injected as a `user` role message when the LLM responds without calling any tools. Reminds the agent to either call `end` or use the appropriate tools. Prevents the agent from stalling in a text-only loop.

### End-Solo Warning Block (`end_solo_warning.md`)

Injected as a `tool` result message when `end` was called alongside other tools. Explains that `end` was stripped, the other tools executed, and the agent must call `end` alone. The `tool_use_id` must match the actual `end` tool call ID in the assistant message.

### Summarization Block (`summarization.md`)

Injected as a `user` role message when context pressure reaches 70%. Asks the agent to condense the important context from this session into `update_memory`, focusing on: active task state, key decisions, remaining work, open questions.

---

## Dangling Tool Use Repair

When a session is interrupted (crash, force-end) after an assistant message with tool calls but before all tool results are saved, the history will have "dangling" tool_use IDs — calls with no matching results.

The Anthropic API returns HTTP 400 if tool_use blocks exist without matching tool_result blocks immediately after. `_repair_dangling_tool_use()` detects this:

```
1. Scan messages for all tool_use IDs in assistant messages
2. Scan for all tool_use_id values in tool messages
3. Compute dangling = issued - resolved
4. For each dangling ID: inject a synthetic tool result:
   "[Session interrupted — tool '{name}' was never executed. Ignore this result.]"
   placed immediately after the assistant message that issued the call
```

This ensures the Anthropic API always receives a valid conversation even after interrupted sessions.

---

## Incoming Message Formatting

`PromptAssembly.format_incoming_messages()` formats raw `ChannelMessage` DB rows into the text block injected as a user message:

```
[Message from {sender_name} ({role}, id={uuid})]: {content}
[Message from User (id=00000000-0000-0000-0000-000000000000)]: {content}
[Message from System (system)]: {assignment_context}
```

For agent senders: `sender_name` = `agent.display_name`, `role` = `agent.role`.
For the user: uses `USER_AGENT_ID` (all-zeros UUID).
For assignment context (no unread messages but active task): a synthetic system message is appended.

---

## Tool Definitions

`PromptAssembly.tools` is populated at construction from `get_tool_defs_for_role(agent.role)` in `backend/tools/loop_registry.py`. Tool definitions are JSON Schema objects sent to the provider as the `tools` parameter (separate from the system prompt string).

**Historical tool name filtering**: when loading history, `_build_history_assistant()` filters out tool calls referencing tool names not in the current `known_tool_names` set. This prevents crashes when tool names are renamed or removed between deployments. The `end` tool is always allowed through regardless of the current registry.

A legacy alias map handles tool renames:
```python
_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "execute_command E2B": "execute_command",
}
```
