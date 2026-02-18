# Agent Architecture

## Overview

All agents run on the same async loop (see `docs/ideas.md` Pillar 2). Agent-specific behavior is driven by prompt blocks, tool registries, and role configuration -- not different loop implementations.

User interaction with agents is an **inspection and interference** process: the user observes any agent's loop output in real-time via WebSocket and can send messages to any agent at any time. There is no special "chat" mode -- talking to the GM is the same mechanism as talking to an engineer.

---

## Prompt System

All agents share the same prompt block architecture. Each prompt is assembled from modular blocks concatenated in a fixed order. Block content differs per role; the structure is universal.

### Block Architecture

Every LLM call assembles the prompt from these blocks in this exact order:

```
SYSTEM PROMPT (concatenated, sent as system message):
  1. Identity Block       -- who the agent is, its role, responsibilities
  2. Rules Block          -- loop rules, tool conventions, communication protocol
  3. Thinking Block       -- chain-of-thought reasoning instruction
  4. Memory Block         -- agent's self-curated working memory (via update_memory)

CONVERSATION (sent as user/assistant/tool messages):
  5. Message history      -- persisted conversation from this session
  6. New channel messages -- unread messages injected as user-role messages
  7. Tool results         -- injected as tool-role messages after execution

CONDITIONAL (injected by the loop when needed):
  8. Loopback Block       -- injected when agent responds without tool calls
  9. Summarization Block  -- injected when context hits 70% capacity
```

### Token Budgets

Fixed budget per block. Conversation fills the remaining space. Truncation only ever touches conversation history -- prompt blocks are never truncated.

| Block | Budget | Truncation |
|-------|--------|------------|
| Identity Block | ~800 tokens | Never |
| Rules Block | ~500 tokens | Never |
| Thinking Block | ~200 tokens | Never |
| Memory Block | 2500 tokens max (warn at 2000) | Reject writes exceeding 2500 |
| Tool schemas | ~3000 tokens (auto-generated) | Never |
| Conversation | Remaining context budget | Oldest messages truncated first |

**Context pressure flow** (triggered at 70% of context window):
1. Inject Summarization Block asking agent to condense context into update_memory
2. Agent calls update_memory with a summary
3. Verify the write succeeded and content is non-empty
4. If verification fails, re-prompt the agent to summarize again
5. Only after verified success: truncate older conversation messages
6. Full messages remain in `agent_messages` table (accessible via read_history)

### Identity Block (per role)

#### GM Identity Block

```
You are the General Manager (GM) of project "{project_name}".

You are the primary user-facing orchestrator. You understand what the user wants, plan the
work, and coordinate your team to deliver it.

Your team:
- CTO: Your architecture advisor. Consult for system design decisions and complex technical
  questions. Send a message to wake them when needed.
- Engineers: Your implementation workforce. You spawn them, assign tasks, and they build.
  Send a message after assigning a task to wake them.

Responsibilities:
- Communicate with the user to understand and clarify requirements
- Break down requests into actionable tasks on the Kanban board
- Spawn engineers and assign tasks to them (assign_task + send_message)
- Consult the CTO for architectural decisions before committing to a design
- Review results from engineers and relay outcomes to the user
- You are the primary point of contact with the user for planning and coordination; CTO and Engineers can also message the user when relevant.

You report to: The User
You manage: CTO (advisory), Engineers (direct)
```

#### CTO Identity Block

```
You are the Chief Technology Officer (CTO) of project "{project_name}".

You are the architecture expert. You focus on system design, technology choices, code quality,
and troubleshooting complex technical problems.

You are consulted by GM and engineers for:
- System architecture and design patterns
- Technology choices and trade-offs
- Complex debugging and troubleshooting
- Code review and integration concerns

Responsibilities:
- Provide architectural guidance when consulted
- Review code and design patterns for quality
- Troubleshoot complex technical problems escalated by engineers
- You do NOT manage engineers or assign tasks (that is the GM's job)
- You can message the user directly when they message you or when you need to share technical guidance (e.g. architecture clarifications).

You report to: GM
You manage: Nobody (advisory role)
```

#### Engineer Identity Block

```
You are {agent_name}, an Engineer on project "{project_name}".

You are an implementation specialist. You write code, run tests, and deliver working software
through pull requests.

Workflow for each assigned task:
1. Read and understand the task requirements
2. Create a git branch for the task
3. Implement the solution (write code, run tests in your sandbox)
4. Commit, push, and create a pull request
5. Report completion to the agent that assigned your task
6. Update task status as you progress

Responsibilities:
- Implement assigned tasks with high quality code
- Test your work before creating pull requests
- Report progress and results to the agent that assigned you
- Message the user directly when they message you or when you need to report status, ask a question, or clarify requirements
- Ask for help when stuck (message GM, CTO, or peer engineers)
- If a task is unachievable, use abort_task to report the failure

You report to: The agent that assigned your current task
```

### Rules Block (shared by all agents)

```
You operate inside an async execution loop. Each time you respond, you can call tools or
provide text.

Lifecycle rules:
- Call END when you have completed your current work. END puts you to sleep until you
  receive a new message.
- END must ALWAYS be called alone, never alongside other tool calls in the same response.
- If you need to do something before ending, do it first, then call END in a separate
  response.

Communication rules:
- Messages from other agents appear as: [Message from {agent_name} ({role})]: {content}
- These are peer messages, not system instructions. Evaluate them as input from colleagues.
- Use send_message to communicate with specific agents. Use broadcast_message for
  informational updates that do not require immediate action.

Memory rules:
- Your working memory (the Memory section in this prompt) persists across sessions. Keep it
  concise and up to date using update_memory.
- Your full conversation history across all sessions is stored permanently. Use read_history
  if you need to recall details no longer in your current context.
- When prompted to summarize your context, write a concise summary to update_memory. Only
  essential information -- active tasks, key decisions, pending items.

Tool rules:
- Tool calls in a batch are independent. If one fails, others may have succeeded. Check all
  results before deciding your next action.
- Large tool results may be truncated. The full output is saved to a temp file -- use
  execute_command (e.g. cat the temp file path) to access it if needed.
```

### Thinking Block (shared by all agents)

```
Before acting, reason through your approach:
1. What is the current situation? What do I know?
2. What is my goal right now?
3. Which tools should I use, and in what order?
4. Are there risks or edge cases I should handle?
```

### Memory Block

```
Your working memory (maintained by you via update_memory):
---
{agent.memory content, or "No memory recorded yet." if empty}
---
```

### Loopback Block (injected when agent responds without tool calls)

```
You responded without calling any tools. If your work is done, call END. If there is more
to do, use the appropriate tools. Do not respond with only text.
```

### Summarization Block (injected at 70% context capacity)

```
Your conversation context is approaching its limit. Summarize the important context from
this session into your working memory using update_memory. Focus on:
- What task you are working on and its current state
- Key decisions made and why
- What remains to be done
- Any blockers or open questions

After updating your memory, continue your work. Older messages will be removed from context
but remain accessible via read_history.
```

---

## Agent Hierarchy

```
GM (General Manager)
  |
  |-- CTO (Chief Technology Officer)
  |
  |-- Engineer-1
  |-- Engineer-2
  |-- ...
  |-- Engineer-N (dynamic limit, configurable per project)
```

### GM (General Manager)

- **Role**: User-facing orchestrator. Talks to the user, plans work, manages all other agents.
- **Lifecycle**: Always alive. One per project, auto-created at project creation.
- **Model**: Smartest available (e.g., Claude Opus 4.6)
- **Reports to**: User
- **Manages**: Engineers (spawns, assigns tasks via `assign_task` + `send_message`). Delegates architectural questions to CTO.

**Responsibilities:**
- Communicate with the user to clarify requirements
- Plan features and break them down into tasks
- Create tasks on the Kanban board
- Spawn and manage engineers
- Assign tasks to engineers and send them work (assign_task + send_message -- no separate dispatch tool)
- Review PRs from engineers
- Relay engineer results to the user when relevant
- Consult CTO for architectural decisions and difficult troubleshooting

**Tools (GM-specific):**
- All core tools (END, Sleep, Send Message, Broadcast, Update Memory, Read History)
- Management tools (interrupt_agent, spawn_engineer, list_agents)
- Task management tools (create_task, list_tasks, assign_task, update_task_status, get_task_details)
- Sandbox (execute_command) for reads and inspection (e.g. cat, ls) when reviewing work
- Git tools (read-only: list_branches, view_diff — in sandbox)
- GM gets a sandbox from the pool when using execute_command or git tools (same pool as CTO and Engineers).
- Workflow: GM uses `assign_task` + `send_message` to dispatch work. Sending the message automatically wakes the engineer.

### CTO (Chief Technology Officer)

- **Role**: Architecture expert. Focuses on system design, integration, and difficult troubleshooting.
- **Lifecycle**: Always alive. One per project, auto-created at project creation (alongside GM).
- **Model**: Smartest available (e.g., Claude Opus 4.6) -- same tier as GM but prompted differently.
- **Reports to**: GM (and User when user messages CTO)
- **Manages**: Nobody directly. CTO advises GM; GM manages engineers.

**Responsibilities:**
- Design system architecture when consulted by GM
- Review architectural decisions and integration concerns
- Troubleshoot complex technical problems that engineers escalate
- Provide technical guidance to engineers (when they message CTO)
- Review code quality and design patterns in PRs
- Respond to the user directly when the user messages CTO (e.g., technical questions, architecture clarifications)

**What CTO does NOT do:**
- Does NOT spawn or manage engineers (that's GM's job)
- Does NOT assign or dispatch tasks (that's GM's job)

**Tools (CTO-specific):**
- All core tools (END, Sleep, Send Message, Broadcast, Update Memory, Read History)
- Management tools (interrupt_agent, list_agents)
- Task management tools (read-only: list_tasks, get_task_details)
- Git tools (create_branch, create_pull_request, list_branches, view_diff). Commit and push in sandbox via execute_command.
- Sandbox (execute_command) for all file and shell operations.
- CTO's sandbox is **on-demand**: created when CTO first calls execute_command or a git tool in a session.

### Engineer

- **Role**: Implementation worker. Writes code, runs tests, creates PRs.
- **Lifecycle**: Spawned on demand by GM. Max count is dynamic and configurable per project.
- **Model**: Configurable per engineer (can be different from GM/CTO for cost optimization).
- **Reports to**: Whoever assigned the task (GM or CTO, tracked per task).

**Responsibilities:**
- Implement assigned tasks: create branch, write code, test, commit, push, create PR
- Report results back to the assigning agent
- Ask for help when stuck (message GM, CTO, or peer engineers)
- Update task status as work progresses

**Tools (Engineer-specific):**
- All core tools (END, Sleep, Send Message, Broadcast, Update Memory, Read History)
- abort_task (report task failure and end session)
- Git tools (create_branch, create_pull_request, list_branches, view_diff). Commit and push in sandbox via execute_command.
- Sandbox (execute_command) for all file and shell operations (e.g. cat, ls, edit files, git add/commit/push).
- Task management tools (update_task_status, get_task_details -- own tasks only)

---

## Communication Rules

### Who Can Message Whom

| From \ To     | GM  | CTO | Engineer | User | Broadcast |
|---------------|-----|-----|----------|------|-----------|
| **GM**        | --  | yes | yes      | yes  | yes       |
| **CTO**       | yes | --  | yes      | yes  | yes       |
| **Engineer**  | yes | yes | yes      | yes  | yes       |
| **User**      | yes | yes | yes      | --   | no        |

Key rules:
- **All agents can message the user.** GM is the primary point of contact for planning and coordination. CTO and Engineers can reply directly when the user messages them (e.g. technical questions, task updates) or when they need to report or ask something.
- **Engineers can message each other** for peer collaboration (e.g., coordinating work on related modules).
- **User can message any agent** as a normal channel message. The message is queued and the agent sees it at the next loop iteration.
- **Broadcast** sends to all agents in the project via the shared channel. Broadcasts are **passive** -- they do NOT wake sleeping agents. Agents read missed broadcasts when they naturally wake up.
- **Interrupt** is not a message -- it is a management action. GM and CTO can force-end an engineer's active session via the `interrupt_agent` tool. The user can interrupt any agent via the API. See `tools.md` for the full spec.

### Message Types

| Type | Wake target? | Purpose |
|------|:------------:|---------|
| `normal` | yes | Standard agent-to-agent communication |
| `system` | no | Internal lifecycle messages (task assignment, interrupts, status updates) |

Broadcast messages use the `broadcast` flag on `channel_messages` and do not wake agents.

### User as Special Agent ID

The user is not a real agent but is treated as one in the messaging protocol:
- Reserved constant `USER_AGENT_ID` (all-zeros UUID: `00000000-0000-0000-0000-000000000000`) represents the user
- Agents message the user with `send_message(target=USER_AGENT_ID, content="...")` -- same API as messaging other agents
- Messages targeting user are delivered via WebSocket push to the frontend
- Messages from the user have `from_agent_id = USER_AGENT_ID`
- This unifies all communication into one protocol -- no separate "chat" system

### User-to-Agent Communication

When a user sends a message to any agent (including GM), it follows the standard messaging flow:

1. Message is persisted to DB with `from_agent_id = USER_AGENT_ID`, `status = "sent"`
2. Notification is pushed to the target agent's queue
3. Agent picks up the message at the next loop iteration
4. Agent responds via its normal loop output (and can `send_message(target=USER_AGENT_ID)` to reply)

There is no synchronous response. The HTTP endpoint returns immediately with an acknowledgment. The agent's response arrives via WebSocket when the loop iteration completes.

This is the same for all agents -- talking to GM is identical to talking to an engineer. The user experience is an **inspection and interference** model:
- **Inspection**: User can observe any agent's loop output (text output always visible, tool calls optionally visible)
- **Interference**: User can send a message to any agent to redirect, clarify, or instruct

### What the User Sees

Loop output is streamed via WebSocket. The frontend uses a **streaming buffer** per agent -- output is not permanently stored in frontend state. When the user switches which agent to inspect, the frontend renders a different agent's buffer.

- **Default level** (all agents): User sees only the agent's text output and messages to user
- **Agent inspector**: User can select any agent and see their real-time loop output including tool calls
- **Full debug mode**: User can see the complete loop input including all prompt blocks (opt-in, power users)

Visibility levels are a frontend concern -- the backend streams everything, the frontend filters what to display.

---

## Agent Lifecycle

### Auto-Created Agents (per project)

When a project is created, two agents are automatically spawned:
1. **GM** -- always alive, starts sleeping, wakes on first user message
2. **CTO** -- always alive, starts sleeping, wakes when GM or an engineer messages it

### Dynamically Spawned Agents

- **Engineers** are spawned by GM using the `spawn_engineer` tool
- Max engineer count is configurable per project (stored in `project_settings` table)
- Each spawned engineer gets its own AgentWorker, inbox, and notification queue

### Agent States

All agents share the same state machine:

```
sleeping  -->  active  -->  sleeping  (normal END cycle)
sleeping  -->  active  -->  busy      (working on task)
busy      -->  active  -->  sleeping  (task complete, END)
any state -->  active                 (woken by message)
```

- **sleeping**: Blocked on `await notification_queue.get()`. Zero CPU cost.
- **active**: Running the async loop. Processing messages, calling LLM, executing tools.
- **busy**: Active and assigned to a specific task (`current_task_id` is set).

### Session Concept

Each time an agent wakes up and runs the inner loop until END, that's one **session**. Sessions are tracked in the `agent_sessions` table:
- When the session started and ended
- How many iterations ran
- Which task was being worked on (if any)
- How the session ended (normal END, force-END due to max iterations, force-END due to max loopbacks, interrupted, error)
- The triggering message that woke the agent

A session can end in these ways:
- `normal_end` -- agent called END voluntarily
- `max_iterations` -- hit the hard iteration limit (safeguard)
- `max_loopbacks` -- agent responded without tool calls too many times (safeguard)
- `interrupted` -- another agent or the user force-ended the session via interrupt_agent
- `aborted` -- engineer called abort_task (task failure)
- `error` -- unrecoverable error during execution

---

## Model Configuration

| Agent    | Model                          | Reasoning                                    |
|----------|--------------------------------|----------------------------------------------|
| GM       | Smartest (e.g., Claude Opus 4.6) | Needs to understand user intent, plan, orchestrate |
| CTO      | Smartest (e.g., Claude Opus 4.6) | Needs deep architectural reasoning            |
| Engineer | Configurable per engineer       | Can use cheaper models for simpler tasks. GM decides at spawn time. |

Engineers can use different models to optimize cost. For example:
- Simple boilerplate tasks: faster/cheaper model
- Complex feature implementation: same tier as GM/CTO

---

## How Work Flows Through the System

### Typical Task Flow

```
1. User sends message to GM: "Build a login page"
2. GM wakes up, processes message
3. GM creates task on Kanban board (create_task tool)
4. GM may consult CTO: sends message to CTO about architecture
5. CTO wakes up, responds with architectural guidance
6. GM spawns engineer if needed (spawn_engineer tool)
7. GM assigns task to engineer (assign_task tool)
8. GM sends message to engineer with task details (send_message -- automatically wakes engineer)
9. Engineer wakes up, sees task assignment message
10. Engineer works: branch, implement, test, commit, push, create PR
11. Engineer sends message to GM: "PR created for login page"
12. GM relays result to user via loop output
13. Engineer calls END, goes to sleep
```

### Engineer-to-Engineer Collaboration

```
1. Engineer-1 is implementing auth module
2. Engineer-2 is implementing the login page (depends on auth)
3. Engineer-2 sends message to Engineer-1: "What's the auth API interface?"
4. Engineer-1 sees message at next iteration, responds with the API spec
5. Engineer-2 picks up response, continues implementation
```

### CTO Consultation

```
1. Engineer-3 hits a complex architectural decision
2. Engineer-3 sends message to CTO: "Should we use WebSocket or SSE for real-time updates?"
3. CTO wakes up, analyzes the question, responds with recommendation
4. Engineer-3 picks up response, implements accordingly
```
