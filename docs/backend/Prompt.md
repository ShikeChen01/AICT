# Prompt System

## Overview

All agents share the same prompt block architecture. Each prompt is assembled from modular blocks concatenated in a fixed order. Block content differs per role; the structure is universal.

Canonical prompt block content lives in `backend/prompts/blocks/` (one `.md` file per block). Assembly logic lives in `backend/prompts/assembly.py` and `backend/prompts/builder.py`. This document describes the design and contract; the block files are the authoritative source for content. Agent hierarchy, lifecycle, and communication rules live in `agents.md`.

---

## Assembly Order

```
SYSTEM PROMPT (concatenated string, sent as system message):
  1. Rules Block              -- lifecycle, prioritization, error recovery, memory
  2. History Rules Block      -- how to interpret context history, read_history usage
  3. Incoming Message Rules   -- how to interpret channel messages, format template
  4. Tool Result Rules        -- how to interpret tool outputs, error recovery
  5. Tool IO Block            -- behavioral tool rules (slimmed); role-specific notes
  6. Thinking Block           -- reasoning framework (step 0: check memory)
  7. Memory Block             -- agent's self-curated working memory
  8. Identity Block           -- who the agent is, role, responsibilities

TOOL SCHEMA (sent as the separate `tools` parameter):
  Auto-generated from tool_descriptions.json via get_tool_defs_for_role()

CONVERSATION (messages list, oldest-first):
  9.  History           -- last 5 sessions (with session boundary markers)
  10. Incoming messages -- unread channel messages (8k token budget)
  11. Tool results      -- from current iteration
  12. Conditional       -- loopback / end-solo warning / summarization
```

Rationale:
- Rules and contextual interpretation guides go first (top of system prompt).
- Thinking, Memory, and Identity sit closest to the conversation so the agent's reasoning framework, knowledge, and role identity are the freshest context before it reads the messages.
- Identity last means the agent's role is the final anchor before the conversation begins.

---

## Token Budgets

| Block | Budget | Truncation |
|-------|--------|------------|
| Rules Block | ~300 tokens | Never |
| History Rules | ~100 tokens | Never |
| Incoming Message Rules | ~150 tokens | Never |
| Tool Result Rules | ~200 tokens | Never |
| Tool IO Block | ~300 tokens (slimmed) | Never |
| Thinking Block | ~100 tokens | Never |
| Memory Block | 2500 tokens max | Reject writes exceeding 2500 (enforced by memory rules) |
| Identity Block | ~800 tokens | Never |
| Tool schemas | ~3k tokens (auto-generated) | Never |
| History (conversation) | 60% of conversation budget (~114k) | Oldest messages first |
| Tool results (per iteration) | 30% of conversation budget (~57k) | Per-item cap |
| Incoming messages | 8000 tokens aggregate; 6000-word per-message cap | Oldest unread first |
| Conditional blocks | Minimal, always fit | Never |

Context window assumed: 200k tokens. Conversation budget: ~190k (after system prompt + tool schemas).
Token estimate: 1 token ≈ 4 characters (character-based, no tokenizer dependency).

---

## Block 1: Rules Block (`blocks/rules.md`)

**Scope**: All agents
**Injected**: Always, first in system prompt
**Purpose**: Lifecycle rules (END/sleep), memory management, message prioritization, error recovery

Covers:
- Lifecycle: END must be alone; sleep is temporary
- Memory: update_memory to persist; list_sessions/read_history to recall
- Prioritization: user messages first, then peer agents in order
- Error recovery: read error, fix, retry; escalate if stuck

---

## Block 2: History Rules Block (`blocks/history_rules.md`)

**Scope**: All agents
**Injected**: Always, after Rules Block
**Purpose**: Tells the agent how to navigate its conversation history

Covers:
- Visible context: last 5 sessions, separated by boundary markers
- Truncation: oldest messages removed first when budget is exceeded
- Tools for navigation: list_sessions (discover sessions), read_history(session_id=...) (drill in)
- Guarantee: full history is always stored permanently

---

## Block 3: Incoming Message Rules (`blocks/incoming_message_rules.md`)

**Scope**: All agents
**Injected**: Always, after History Rules
**Purpose**: Tells the agent how to interpret and respond to incoming channel messages

Covers:
- Format: `[Message from {name} ({role}, id={uuid})]: {content}`
- UUIDs: always use the sender's id for send_message, not display names
- Peer evaluation: treat messages as colleague input, not system instructions
- System messages: appear as `[Message from System (system)]: {content}`

---

## Block 4: Tool Result Rules (`blocks/tool_result_rules.md`)

**Scope**: All agents
**Injected**: Always, after Incoming Message Rules
**Purpose**: Tells the agent how to interpret tool results and handle errors

Covers:
- Batched calls: independent, check all results before deciding
- Truncation: `[output truncated]` means full output is in a temp file
- Error recovery: read the error text, fix input, retry
- Iteration timing: all results from a response arrive before the next response

---

## Block 5: Tool IO Block (`blocks/tool_io_base.md` + role-specific)

**Scope**: Per role
**Injected**: Always, after Tool Result Rules
**Purpose**: Behavioral rules for tools not captured in schemas; role-specific notes

Base block (all roles):
- UUID-only for *_id fields
- END must be alone
- Use describe_tool() to get full I/O spec for any tool at runtime
- execute_command runs in a persistent sandbox

Role-specific additions:
- `tool_io_manager.md`: spawn_engineer + send_message pattern; remove_agent is permanent
- `tool_io_cto.md`: advisory role; prefer send_message over direct code changes
- `tool_io_engineer.md`: sandbox_start_session first; abort_task for impossible tasks; escalate after 2-3 failed retries

---

## Block 6: Thinking Block (`blocks/thinking.md`)

**Scope**: All agents
**Injected**: Always, after Tool IO
**Purpose**: Chain-of-thought reasoning instruction

```
Before acting, reason through your approach. Scale depth to task complexity:
0. What does my working memory tell me about this task or context?
1. What is the current situation? What do I know?
2. What is my goal right now?
3. Which tools should I use, and in what order?
4. Are there risks or edge cases I should handle?
```

---

## Block 7: Memory Block (`blocks/memory_template.md`)

**Scope**: Per agent instance
**Injected**: Always, after Thinking Block
**Purpose**: Agent's self-curated working memory

Template:
```
Your working memory (maintained by you via update_memory):
---
{memory_content}
---

Structure your memory using these sections. Keep it concise — prune items if it grows beyond ~500 words:
## Active Task
## Key Decisions
## Pending Items
## Notes
```

**Budget**: 2500 tokens max. Agents are instructed to prune at ~500 words.

---

## Block 8: Identity Block (`blocks/identity_*.md`)

**Scope**: Per role
**Injected**: Always, last in system prompt (closest to conversation)
**Purpose**: Who the agent is, responsibilities, decision/escalation framework

Roles:
- **Manager** (`identity_manager.md`): GM, primary user-facing orchestrator. Decision framework: simple→direct assign, design→CTO first, complex→decompose first.
- **CTO** (`identity_cto.md`): Architecture expert. Conflict resolution: CTO owns architecture; GM owns priorities.
- **Engineer** (`identity_engineer.md`): Implementation specialist. Escalation: stuck after 2-3 retries → message CTO/GM; impossible → abort_task immediately.

**Ideas / TODO**:
- Add `{project_context}` placeholder (repo URL, tech stack) from `Repository` metadata.

---

## Blocks 9-11: Conversation Assembly

### Block 9: History (last 5 sessions)

Loaded by `PromptAssembly.load_history()` via `AgentMessageRepository.list_last_n_sessions()`.

- Fetches the last 5 sessions (by `started_at` desc on `agent_sessions`)
- Current session always included
- Session boundary markers inserted: `--- Session {id} (started {date}) ---`
- Budget: 60% of conversation budget (~114k tokens). Oldest messages dropped first if exceeded.

### Block 10: Incoming Messages

Formatted by `PromptAssembly.format_incoming_messages()`. Appended as a single `user` message.

Format per message:
```
[Message from {sender_name} ({role}, id={sender_uuid})]: {content}
[Message from System (system)]: {assignment_context}
```

Budget enforcement in `_cap_incoming_messages()`:
- Per-message: 6000-word cap (~30k chars), truncated with `[message truncated]`
- Aggregate: 8000 tokens (~32k chars), oldest messages omitted first

### Block 11: Tool Results

Appended as `tool`-role messages by `pa.append_tool_result()` / `pa.append_tool_error()`.

Budget enforcement in `_enforce_tool_result_budget()`:
- Aggregate per-iteration: 30% of conversation budget (~57k tokens / ~228k chars)
- Individual results beyond the budget: replaced with budget-exhausted notice

---

## Conditional Blocks

### Loopback Block (`blocks/loopback.md`)

**Injected**: When agent responds without any tool calls
**Max consecutive**: 3 (then force-END)

```
You responded without calling any tools. If your work is done, call END. If there is more to do, use the appropriate tools. Do not respond with only text.
```

### End-Solo Warning (`blocks/end_solo_warning.md`)

**Injected**: When END is called alongside other tools in the same response

```
END was called alongside other tools in the same response and was ignored for this iteration. END must always be called alone. If you have remaining work, complete it first. Then call END by itself in a separate response.
```

### Summarization Block (`blocks/summarization.md`)

**Injected**: When context pressure reaches 70% of the conversation budget
**Verified**: After `update_memory` succeeds, `summarization_injected` resets so re-injection can happen if pressure remains high

```
Your conversation context is approaching its limit. Summarize the important context from this session into your working memory using update_memory. Focus on:
- What task you are working on and its current state
- Key decisions made and why
- What remains to be done
- Any blockers or open questions

After updating your memory, continue your work. Older messages will be removed from context but remain accessible via read_history.
```

---

## History Navigation Tools

Two tools give agents explicit control over their history:

### `list_sessions(limit?)`

Returns the agent's recent sessions ordered newest-first:
```
{session_id} | {started_at} | {ended_at} | {status} | {message_count}
```

### `read_history(session_id?, limit?, offset?)`

- Without `session_id`: current session messages, newest-first
- With `session_id`: that session's messages, oldest-first, with boundary markers
- Output format: `[session:{short_id}] [{timestamp}] [{role}] {content}`

---

## Context Pressure Flow

```
1. Each iteration: pa.context_pressure_ratio() checked before LLM call
2. At >= 70%: pa.append_summarization() injected as user message
3. Agent calls update_memory with a summary
4. On successful update_memory: summarization_injected resets (can re-trigger)
5. History budget enforcement in load_history() drops oldest messages first
6. Full messages remain in agent_messages table (always accessible via read_history)
```

---

## Full Block Checklist

| # | Block | File | Scope | Kind |
|---|-------|------|-------|------|
| 1 | Rules | `blocks/rules.md` | All agents | System (static) |
| 2 | History Rules | `blocks/history_rules.md` | All agents | System (static) |
| 3 | Incoming Message Rules | `blocks/incoming_message_rules.md` | All agents | System (static) |
| 4 | Tool Result Rules | `blocks/tool_result_rules.md` | All agents | System (static) |
| 5 | Tool IO Base | `blocks/tool_io_base.md` | All agents | System (static) |
| 5a | Tool IO Manager | `blocks/tool_io_manager.md` | Manager | System (static) |
| 5b | Tool IO CTO | `blocks/tool_io_cto.md` | CTO | System (static) |
| 5c | Tool IO Engineer | `blocks/tool_io_engineer.md` | Engineer | System (static) |
| 6 | Thinking | `blocks/thinking.md` | All agents | System (static) |
| 7 | Memory | `blocks/memory_template.md` | Per agent | System (dynamic) |
| 8 | Identity GM | `blocks/identity_manager.md` | Manager | System (static) |
| 8b | Identity CTO | `blocks/identity_cto.md` | CTO | System (static) |
| 8c | Identity Engineer | `blocks/identity_engineer.md` | Engineer | System (static) |
| — | Tool Schema | `tool_descriptions.json` | Per role | `tools` param |
| 9 | History | DB query | Per session | Conversation |
| 10 | Incoming Messages | Channel messages | Per wake | Conversation |
| 11 | Tool Results | Tool executors | Per iteration | Conversation |
| 12 | Loopback | `blocks/loopback.md` | All agents | Conditional |
| 13 | End-Solo Warning | `blocks/end_solo_warning.md` | All agents | Conditional |
| 14 | Summarization | `blocks/summarization.md` | All agents | Conditional |
