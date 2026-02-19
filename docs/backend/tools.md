# Tool System

## Overview

Tools are the agent's interface to the outside world. Every action an agent takes -- sending a message, running a command in the sandbox, creating a git branch -- goes through a tool call. The LLM decides which tools to call; the async loop executes them and returns results.

Tools are organized into four categories:
1. **Core Tools** -- available to all agents (lifecycle, communication, memory)
2. **Management Tools** -- agent and session management (GM, CTO)
3. **Task Tools** -- Kanban board operations (scoped by role)
4. **Code Tools** -- git (branch/PR and read-only) and sandbox (execute_command for all agents)

See the Tool Registry at the bottom of this document for the full role-to-tool permission matrix.

---

## Tool Checklist

Quick reference for all tools. Drop ideas/notes in the right column.

| # | Tool | Category | Roles | Spec Status | Ideas / Notes |
|---|------|----------|-------|-------------|---------------|
| 1 | `end` | Core | All | Done | |
| 2 | `sleep` | Core | All | Done | |
| 3 | `send_message` | Core | All | Done | |
| 4 | `broadcast_message` | Core | All | Done | |
| 5 | `update_memory` | Core | All | Done | |
| 6 | `read_history` | Core | All | Done | |
| 7 | `interrupt_agent` | Management | GM, CTO | Done | |
| 8 | `abort_task` | Management | Engineer | Done | |
| 9 | `spawn_engineer` | Management | GM, CTO | Done | |
| 10 | `list_agents` | Management | GM, CTO | Done | |
| 11 | `create_task` | Task | GM | Done | |
| 12 | `list_tasks` | Task | All (scoped) | Done | |
| 13 | `assign_task` | Task | GM | Done | |
| 14 | `update_task_status` | Task | GM, Engineer(own) | Done | |
| 15 | `get_task_details` | Task | All | Done | |
| 16 | `create_branch` | Git | CTO, Engineer | Done | |
| 17 | `create_pull_request` | Git | CTO, Engineer | Done | |
| 18 | `list_branches` | Git | All | Done | |
| 19 | `view_diff` | Git | All | Done | |
| 20 | `execute_command` | Sandbox | All | Done | commit/push and file ops via sandbox |
| 21 | `describe_tool` | Introspection | All | Done | On-demand tool documentation |

---

## Execution Policies

### Context Injection

Every tool needs runtime context (agent_id, project_id, sandbox_id, repository info). Tools are stateless functions. Context is bound at assembly time using a factory pattern:

```
def build_tools(agent: Agent, project: Repository) -> list[Tool]:
    ctx = ToolContext(
        agent_id=agent.id,
        project_id=project.id,
        sandbox_id=agent.sandbox_id,
        repo_url=project.code_repo_url,
    )
    return [
        send_message.bind(ctx),
        update_memory.bind(ctx),
        execute_command.bind(ctx),
        ...
    ]
```

The `ToolContext` is created once per session and passed to all tools. Tools never read global state.

### Tool Result Handling

Tool results are injected into the conversation as tool-role messages. Large results are a context window risk.

**Policy**: Every tool result is checked against `MAX_TOOL_RESULT_TOKENS` (4000 tokens). If the result exceeds this limit:

1. The full result is written to a temp file in the agent's sandbox: `/tmp/aict/{tool_name}_{timestamp}.txt`
2. The agent receives a truncated result with a header:
   ```
   [Result truncated -- {total_lines} lines, stored at /tmp/aict/{tool_name}_{timestamp}.txt]
   {first_100_lines_of_output}
   ```
3. The agent can use `execute_command` (e.g. `cat` the temp file path) to access the full result if needed
4. Temp files are cleaned up automatically when the session ends

This keeps the context window clean while preserving full results for on-demand access.

### Concurrency

The async loop executes all tool calls from a single LLM response concurrently (except END, see below). Some tool combinations are unsafe when run in parallel.

**Concurrency classification**:
| Safe to parallelize | Must serialize |
|---------------------|----------------|
| list_tasks | All git tools (sequential) |
| get_task_details | execute_command (per-sandbox) |
| read_history | |

### Error Handling

All tool results (success and failure) are returned to the agent. The loop never silently swallows errors.

- If a tool fails, the error message is returned as the tool result. The agent sees it and reacts.
- If multiple tools are called in a batch and one fails, the others still execute. All results (including the error) are returned.
- The agent's Rules Block instructs: "Tool calls in a batch are independent. If one fails, others may have succeeded. Check all results."

### Timeouts

Every tool has a default execution timeout. If a tool exceeds its timeout, execution is cancelled and a timeout error is returned as the tool result.

| Tool category | Default timeout |
|---------------|----------------|
| Git operations | 60 seconds |
| Sandbox commands | 120 seconds |
| Message/memory | 10 seconds |
| Task operations | 10 seconds |

---

## Execution Backends

All code tools (remaining git tools and `execute_command`) run inside the agent's E2B sandbox. File and git commit/push operations are done via `execute_command` (e.g. `cat`, `ls`, `git add`, `git commit`, `git push`). This keeps a single execution environment for every agent.

### E2B Sandbox

- **Operations**: `execute_command` (all agents), plus git tools `create_branch`, `create_pull_request`, `list_branches`, `view_diff`
- **Used by**: GM, CTO, and Engineers. All agents get a sandbox from the project-wide pool when they first use a sandbox or git tool (see Sandbox Pool below).
- GM uses the sandbox for reads and inspection (e.g. `cat`, `ls`, `git diff`) and read-only git tools. CTO and Engineers use it for full workflow including commit/push and file edits via shell commands.

---

## Core Tools

Available to ALL agents. These handle lifecycle, communication, and memory.

### end

Signals that the agent has completed its current work. Breaks the inner loop. Agent goes to sleep until a new message wakes it.

```
end()
  Parameters: none
  Returns: nothing (loop breaks)
```

**Programmatic enforcement**: END must always be a solo tool call. If the LLM returns END alongside other tool calls in the same response:
1. Strip END from the batch
2. Execute all other tools normally
3. Inject a system note: "END was called alongside other tools. Other tools were executed. Call END alone when you are finished."
4. Continue the loop (do not break)

This is enforced in the loop code, not just in the prompt.

### sleep

Pauses the agent for a specified duration, then resumes the loop. Different from END: sleep is temporary (agent resumes automatically), END is indefinite (agent waits for a message).

```
sleep(duration_seconds: int)
  Parameters:
    duration_seconds  int  required  How long to sleep (max 3600)
  Returns: "Slept for {duration_seconds} seconds. Resuming."
```

### send_message

Sends a message to another agent. The message is persisted to DB immediately and a wake-up notification is pushed to the target agent's queue. The target agent reads the message from DB at its next loop iteration.

```
send_message(target_agent_id: str, content: str)
  Parameters:
    target_agent_id  str  required  UUID of the target agent (use USER_AGENT_ID for user)
    content          str  required  Message content
  Returns: "Message sent to {target_agent_name}."
```

- Sending to `USER_AGENT_ID` delivers the message via WebSocket to the frontend
- Sending to a sleeping agent wakes them up
- The agent's Rules Block lists who it can message (see agents.md Communication Rules)

### broadcast_message

Sends a message to all agents in the project via the shared broadcast channel. Broadcast messages are **passive** -- they do NOT wake sleeping agents. Agents read missed broadcasts when they naturally wake up for other reasons.

```
broadcast_message(content: str)
  Parameters:
    content  str  required  Message content
  Returns: "Broadcast sent to all agents."
```

Use broadcasts for informational updates that don't require immediate action (e.g., "Auth module API finalized, interface spec attached").

### update_memory

Overwrites the agent's Self-Define Memory Block (Layer 1 memory). This block is included in the system prompt on every iteration, so it serves as the agent's persistent working memory across sessions.

```
update_memory(content: str)
  Parameters:
    content  str  required  New memory content (replaces existing)
  Returns: "Memory updated ({token_count} tokens)." or error if exceeds cap
```

**Size enforcement**:
- Hard cap: 2500 tokens. Writes exceeding this are rejected with an error.
- Soft cap: 2000 tokens. If memory exceeds 2000 tokens after write, the agent receives a warning: "Memory is at {token_count}/2500 tokens. Consider condensing."
- The context window summarization flow (triggered at 70% capacity) prompts the agent to update_memory before truncating conversation history. The agent should keep memory concise and curated.

### read_history

Queries the agent's own persistent message log (`agent_messages` table). This is Layer 2 memory -- every prompt, response, tool call, and result from all sessions is stored here.

```
read_history(limit: int = 20, offset: int = 0, session_id: str | null = null)
  Parameters:
    limit       int          optional  Max messages to return (default 20, max 100)
    offset      int          optional  Skip first N messages (default 0)
    session_id  str | null   optional  Filter to a specific session (default: all sessions)
  Returns: list of messages with role, content, tool info, timestamp, iteration number
```

The agent's Rules Block tells it: "Your full conversation history is stored. Use read_history to recall past details that are no longer in your current context."

---

## Management Tools

### interrupt_agent

Force-ends another agent's current session. The target agent's loop is signaled to break at the next iteration boundary (not mid-execution -- the current LLM call or tool execution finishes first). A system message is logged in `channel_messages` recording the interruption.

```
interrupt_agent(target_agent_id: str, reason: str)
  Parameters:
    target_agent_id  str  required  UUID of the agent to interrupt
    reason           str  required  Why the interruption is needed
  Returns: "Agent {name} interrupted. Session ended."
```

**Available to**: GM, CTO (and User via API, not a tool)

**Behavior**:
1. Sets an interrupt flag on the target agent's worker
2. The target's loop checks this flag at the start of each iteration
3. If set: the loop breaks, session ends with `end_reason = "interrupted"`
4. A system channel message is stored: "Session interrupted by {agent_name}: {reason}"
5. The interrupter can then send a regular message to re-awaken the agent with new instructions

**Constraints**:
- Cannot interrupt yourself
- If target is already sleeping, returns: "Agent {name} is not active. No session to interrupt."
- The target's current iteration completes before the session ends (no mid-execution abort)

### abort_task

Reports task failure and ends the session. Combines three actions atomically: updates task status, notifies the task assigner, and ends the session. This prevents partial state where the agent fails but forgets to notify.

```
abort_task(reason: str)
  Parameters:
    reason  str  required  Why the task cannot be completed
  Returns: nothing (session ends)
```

**Available to**: Engineers (the agent must have a `current_task_id` set)

**Behavior**:
1. Updates the task status to `aborted`
2. Sends a channel message to the task's `created_by_id` agent: "Task '{task_title}' aborted: {reason}"
3. Clears the agent's `current_task_id`
4. Ends the session (same as END)

If the agent has no current task, returns an error: "No active task to abort."

### spawn_engineer

Creates a new engineer agent in the project. The engineer gets its own AgentWorker, sandbox, inbox, and notification queue. It is started immediately and ready to receive messages or task assignments.

```
spawn_engineer(display_name: str, model?: str, tier?: str)
  Parameters:
    display_name  str  required  Name for the engineer (e.g. "Engineer-3")
    model         str  optional  LLM model override for the engineer
    tier          str  optional  Engineer tier (e.g. "junior", "senior"); influences default model via project settings
  Returns: "Engineer spawned: {uuid}\nThe engineer is now awake. Send it a message or assign a task to give it work."
```

**Available to**: GM, CTO

**Constraints**:
- Maximum 5 engineers per project (checks `project_settings.max_engineers`). Returns error if at limit.
- The engineer is spawned and its worker started immediately.

### list_agents

Lists all agents in the project with their current status, role, and assigned task.

```
list_agents()
  Parameters: none
  Returns: table of agents with id, display_name, role, status, current_task
```

**Available to**: GM, CTO

---

## Task Tools

Operations on the Kanban board (`tasks` table). Access is scoped by role.

### create_task

Creates a new task on the Kanban board.

```
create_task(title: str, description: str = null, critical: int = 5, urgent: int = 5, parent_task_id: str = null)
  Parameters:
    title          str        required  Task title
    description    str        optional  Detailed description
    critical       int (0-10) optional  Criticality (0 = most critical, default 5)
    urgent         int (0-10) optional  Urgency (0 = most urgent, default 5)
    parent_task_id str        optional  Parent task UUID for subtask hierarchy
  Returns: "Task created: '{title}' (id: {uuid})"
```

**Available to**: GM

### list_tasks

Lists tasks with optional filters.

```
list_tasks(status: str = null, assigned_to: str = null)
  Parameters:
    status       str  optional  Filter by status (backlog, assigned, in_progress, etc.)
    assigned_to  str  optional  Filter by assigned agent UUID
  Returns: table of tasks with id, title, status, critical/urgent (2D priority), assigned agent
```

**Available to**: GM, CTO, Engineers (Engineers see all tasks but can only modify their own)

### assign_task

Assigns a task to an engineer. Sets `assigned_agent_id` on the task and updates status to `assigned`. Does NOT automatically wake the engineer -- GM should follow up with `send_message` to wake and instruct the engineer.

```
assign_task(task_id: str, agent_id: str)
  Parameters:
    task_id   str  required  UUID of the task
    agent_id  str  required  UUID of the engineer to assign
  Returns: "Task '{title}' assigned to {agent_name}."
```

**Available to**: GM

### update_task_status

Updates the status of a task.

```
update_task_status(task_id: str, status: str)
  Parameters:
    task_id  str  required  UUID of the task
    status   str  required  New status: backlog | specifying | assigned | in_progress | in_review | done | aborted
  Returns: "Task '{title}' status updated to {status}."
```

**Available to**: GM (any task), Engineers (own assigned tasks only)

### get_task_details

Gets full details of a specific task.

```
get_task_details(task_id: str)
  Parameters:
    task_id  str  required  UUID of the task
  Returns: full task object (title, description, status, critical/urgent, assigned agent, branch, PR URL, subtasks)
```

**Available to**: GM, CTO, Engineers

---

## Code Tools

### Git Tools

All git operations execute inside the agent's E2B sandbox against the project repository.

#### create_branch

Creates a new git branch from the default branch.

```
create_branch(branch_name: str)
  Parameters:
    branch_name  str  required  Name of the branch to create
  Returns: "Branch '{branch_name}' created from {default_branch}."
```

#### create_pull_request

Creates a pull request from the current branch to the default branch.

```
create_pull_request(title: str, description: str = "")
  Parameters:
    title        str  required  PR title
    description  str  optional  PR description body
  Returns: "PR created: {pr_url}"
```

#### list_branches

Lists all branches in the repository.

```
list_branches()
  Parameters: none
  Returns: list of branch names with current branch marked
```

#### view_diff

Shows the diff between two refs (branches, commits, or HEAD).

```
view_diff(base: str = "main", head: str = "HEAD")
  Parameters:
    base  str  optional  Base ref (default: main)
    head  str  optional  Head ref (default: HEAD)
  Returns: unified diff output (subject to result truncation policy)
```

**Git tool availability**:
- Engineers, CTO: create_branch, create_pull_request, list_branches, view_diff (in sandbox). Commit and push are done via `execute_command` (e.g. `git add`, `git commit`, `git push`).
- GM: read-only (list_branches, view_diff) in sandbox. GM uses `execute_command` for any file reads (e.g. `cat`, `ls`) in the sandbox.

### Sandbox Tools

#### execute_command

Runs a shell command in the agent's E2B sandbox.

```
execute_command(command: str, timeout: int = 120)
  Parameters:
    command  str  required  Shell command to execute
    timeout  int  optional  Max execution time in seconds (default 120, max 300)
  Returns: stdout + stderr output (subject to result truncation policy)
```

**Available to**: All agents (GM, CTO, Engineers). GM uses the sandbox for reads (e.g. `cat`, `ls`) when reviewing; CTO and Engineers use it for full workflow including file edits and git commit/push via shell commands.

---

## Tool Registry

Complete role-to-tool permission matrix.

| Tool | GM | CTO | Engineer |
|------|:--:|:---:|:--------:|
| **Core** | | | |
| end | yes | yes | yes |
| sleep | yes | yes | yes |
| send_message | yes | yes | yes |
| broadcast_message | yes | yes | yes |
| update_memory | yes | yes | yes |
| read_history | yes | yes | yes |
| **Management** | | | |
| interrupt_agent | yes | yes | -- |
| abort_task | -- | -- | yes |
| spawn_engineer | yes | yes | -- |
| list_agents | yes | yes | -- |
| **Task** | | | |
| create_task | yes | -- | -- |
| list_tasks | yes | read | read |
| assign_task | yes | -- | -- |
| update_task_status | any | -- | own |
| get_task_details | yes | yes | yes |
| **Git** | | | |
| create_branch | -- | yes | yes |
| create_pull_request | -- | yes | yes |
| list_branches | yes | yes | yes |
| view_diff | yes | yes | yes |
| **Sandbox** | | | |
| execute_command | yes | yes | yes |
| **Introspection** | | | |
| describe_tool | yes | yes | yes |

**Legend**: `yes` = full access, `read` = read-only variant, `own` = scoped to own resources, `--` = no access

Remaining git tools and `execute_command` run in the agent's E2B sandbox. GM, CTO, and Engineers all participate in the sandbox pool (see Sandbox Pool).

---

## Sandbox Pool

GM, CTO, and Engineers all use sandboxes for code work (execute_command and git tools). Sandboxes are acquired on demand from a project-wide pool.

### Persistent Sandbox Slots

`project_settings.persistent_sandbox_count` controls how many sandbox slots survive across sessions (agent sleep/wake cycles). These slots are allocated **first-come-first-serve**, not by role.

### Allocation Flow

1. Agent needs a sandbox (first execute_command or git tool call in a session — GM, CTO, or Engineer)
2. Check for a free persistent slot → if available, assign it
3. No free persistent slot → create a non-persistent sandbox (destroyed at session end)
4. Agent finishes (session END) and holds a persistent slot → slot is released
5. If another agent currently has a non-persistent sandbox → promote it to persistent

### Example (persistent_sandbox_count = 1)

```
GM wakes, needs sandbox     → gets the 1 persistent slot (e.g. execute_command for cat/ls when reviewing)
Engineer wakes, needs sandbox → no persistent slot available, gets non-persistent
GM finishes, releases slot  → engineer's sandbox is promoted to persistent
Engineer sleeps, wakes later  → sandbox is still alive (persistent)
```

### Sandbox Lifecycle

- **Persistent sandbox**: survives agent sleep/wake cycles. Repo state preserved between sessions. Agent runs `git pull` at session start to sync.
- **Non-persistent sandbox**: created when agent first needs a sandbox in a session, destroyed at session end. Repo is cloned fresh (shallow clone for speed).
- **GM**: gets a sandbox from the pool when using execute_command or read-only git tools (list_branches, view_diff). Same pool as CTO and Engineers.
- **CTO on-demand**: sandbox is created on first execute_command or git tool call in a session.

### Isolation

Each agent that has a sandbox gets its own. There are no shared sandboxes. The project repository is cloned into each sandbox at creation time.
