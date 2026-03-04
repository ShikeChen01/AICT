# Frontend Architecture & Integration Specification

## Overview

The AICT frontend is a React single-page application that provides the user interface for interacting with the multi-agent AI development team. The user's primary interaction model is **inspection and interference**: observe any agent's real-time output and send messages to any agent at any time.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 19 + TypeScript |
| Build | Vite 7 |
| Styling | Tailwind CSS 4 |
| Routing | React Router 7 |
| State | React hooks + context (no external state library) |
| Auth | Firebase Authentication (Google OAuth); GitHub token per-user in User Settings |
| Real-time | Native WebSocket |
| Drag & Drop | @dnd-kit |
| Graph Visualization | @xyflow/react + dagre |
| Markdown | react-markdown + remark-gfm |
| Animations | framer-motion |
| Icons | lucide-react |
| Testing | Vitest (unit) + Playwright (e2e) |

### Design Principles

1. **Agent-centric, not chat-centric** -- the UI is organized around agents and their work, not a single chat thread. The user can observe and message any agent.
2. **Streaming-first** -- agent output arrives via WebSocket in real-time. There are no synchronous "wait for response" interactions. The UI is always responsive.
3. **Buffer, don't store** -- agent stream output is held in an ephemeral buffer per agent, not permanently stored in React state. When the user switches agents, the buffer switches. Historical data comes from the API.
4. **Progressive disclosure** -- default view shows agent text output and messages. Inspector mode reveals tool calls. Debug mode reveals full prompt blocks. These are frontend visibility toggles; the backend streams everything.

---

## Directory Structure

```
frontend/
├── src/
│   ├── main.tsx                          # React entry point
│   ├── App.tsx                           # Root layout, routing, global state
│   ├── index.css                         # Tailwind base styles
│   │
│   ├── api/
│   │   └── client.ts                     # REST client + WebSocket client
│   │
│   ├── config/
│   │   └── firebase.ts                   # Firebase initialization
│   │
│   ├── contexts/
│   │   ├── AuthContext.tsx                # Firebase auth state provider
│   │   ├── ProjectContext.tsx             # Active project context (NEW)
│   │   └── AgentStreamContext.tsx         # WebSocket stream manager (NEW)
│   │
│   ├── hooks/
│   │   ├── index.ts                      # Re-exports
│   │   ├── useAgents.ts                  # Agent list + status polling
│   │   ├── useWebSocket.ts               # WebSocket connection manager
│   │   ├── useTasks.ts                   # Kanban task state
│   │   ├── useMessages.ts               # Agent message history (NEW)
│   │   ├── useAgentStream.ts            # Live agent output buffer (NEW)
│   │   └── useSessions.ts              # Session history queries (NEW)
│   │
│   ├── pages/
│   │   ├── index.ts                      # Re-exports
│   │   ├── Login.tsx                     # Firebase login
│   │   ├── Register.tsx                  # Firebase registration
│   │   ├── AuthCallback.tsx              # OAuth callback handler
│   │   ├── Projects.tsx                  # Repository list + create/import
│   │   ├── Settings.tsx                  # Project settings (agents, sandboxes)
│   │   ├── UserSettings.tsx              # User profile + GitHub token
│   │   └── Workspace.tsx                 # Main workspace layout (NEW)
│   │
│   ├── components/
│   │   ├── MarkdownContent.tsx           # Shared markdown renderer
│   │   │
│   │   ├── Workspace/                    # Main workspace layout (NEW)
│   │   │   ├── WorkspaceLayout.tsx       # Three-column layout shell
│   │   │   ├── Sidebar.tsx               # Project selector + navigation
│   │   │   └── ConnectionStatus.tsx      # WebSocket connection indicator
│   │   │
│   │   ├── AgentChat/                    # Agent messaging (NEW, replaces Chat/)
│   │   │   ├── AgentChatView.tsx         # Conversation with an agent
│   │   │   ├── MessageList.tsx           # Message history display
│   │   │   ├── MessageInput.tsx          # User message composer
│   │   │   ├── AgentStream.tsx           # Live streaming output display
│   │   │   └── AgentSelector.tsx         # Pick which agent to talk to
│   │   │
│   │   ├── Agents/                       # Agent management
│   │   │   ├── AgentsPanel.tsx           # Agent roster with status
│   │   │   ├── AgentCard.tsx             # Single agent status card (NEW)
│   │   │   ├── AgentInspector.tsx        # Deep agent inspection view
│   │   │   └── index.ts
│   │   │
│   │   ├── Kanban/                       # Task board
│   │   │   ├── KanbanBoard.tsx           # Full board with columns
│   │   │   ├── Column.tsx                # Single status column
│   │   │   ├── TaskCard.tsx              # Draggable task card
│   │   │   ├── TaskModal.tsx             # Task detail modal
│   │   │   ├── CreateTaskModal.tsx        # New task form
│   │   │   └── index.ts
│   │   │
│   │   ├── Workflow/                     # Agent topology graph
│   │   │   ├── WorkflowGraph.tsx         # xyflow graph visualization
│   │   │   ├── AgentNode.tsx             # Custom node for agents
│   │   │   ├── ToolNode.tsx              # Custom node for tool execution
│   │   │   └── index.ts
│   │   │
│   │   ├── ActivityFeed/                 # Debug activity log
│   │   │   ├── ActivityFeed.tsx          # Scrollable activity stream
│   │   │   └── index.ts
│   │   │
│   │   └── Artifacts/                    # File browser
│   │       ├── ArtifactBrowser.tsx       # Repo file tree + viewer
│   │       └── index.ts
│   │
│   ├── types/
│   │   └── index.ts                      # TypeScript interfaces
│   │
│   └── test/
│       ├── setup.ts                      # Vitest setup
│       └── mocks.ts                      # Shared test mocks
│
├── e2e/                                  # Playwright end-to-end tests
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── vitest.config.ts
```

### Files to Drop (Deprecated)

| File/Directory | Replacement |
|----------------|-------------|
| `components/Chat/` | `components/AgentChat/` (agent-targeted messaging) |
| `components/TicketChat/` | Dropped (tickets deprecated) |
| `hooks/useChat.ts` | `hooks/useMessages.ts` + `hooks/useAgentStream.ts` |
| `hooks/useTicketChat.ts` | Dropped |
| `types/` ticket-related types | Dropped |

---

## Routing

```
/                                → Redirect to /repository/{first}/workspace
/login                           → LoginPage
/register                        → RegisterPage
/auth/callback                   → AuthCallbackPage

/repositories                    → ProjectsPage (list, create, import)
/settings                        → UserSettingsPage

/repository/:projectId/workspace → WorkspacePage (default: agent chat view)
/repository/:projectId/kanban    → WorkspacePage (kanban view)
/repository/:projectId/workflow  → WorkspacePage (workflow graph view)
/repository/:projectId/artifacts → WorkspacePage (file browser view)
/repository/:projectId/settings  → SettingsPage (project config)
```

All `/repository/:projectId/*` routes share the same `WorkspacePage` layout. The workspace has a sidebar, a main content area, and an agents panel. The active view is determined by the URL path segment.

---

## Core Architecture

### State Management Strategy

No external state library (Redux, Zustand, etc.). State is managed through:

1. **React Context** for global concerns (auth, active project, WebSocket)
2. **Custom hooks** for feature-specific state (agents, tasks, messages, streams)
3. **Component-local state** for UI concerns (modals, selections, input values)
4. **WebSocket event handlers** for real-time updates (push, not poll)
5. **API calls** for initial data loads and user actions

### Context Hierarchy

```
<AuthProvider>                    # Firebase auth state
  <ProjectProvider>               # Active project + project list
    <AgentStreamProvider>         # WebSocket connection + stream buffers
      <App />
    </AgentStreamProvider>
  </ProjectProvider>
</AuthProvider>
```

---

## Auth Flow

### Login

User identity uses the current mechanism: Google OAuth via Firebase. There is no separate login API endpoint.

1. User clicks "Continue with Google" on `/login`
2. Firebase `signInWithPopup` with Google provider; Firebase returns the user and ID token
3. Frontend gets the ID token via `user.getIdToken()`, stores it in memory and `localStorage`, and sends it as `Authorization: Bearer <token>` on all API requests
4. Backend verifies the token with Firebase Admin SDK and resolves the user (no separate login endpoint)
5. Frontend redirects to `/repositories` (or the last visited project)

### GitHub token (per-user setting)

The GitHub Personal Access Token is **not** part of login. It is configured **per user** in **User Settings** (`/settings`). The backend uses it for repository creation, import, cloning, and E2B sandbox repo access. The UI shows a masked input; the API returns only `github_token_set` (boolean), never the token value.

### Token Management

```typescript
// In-memory token (primary), localStorage (persistence across page reloads)
let authToken: string | null = null;

function setAuthToken(token: string | null): void {
  authToken = token;
  if (token) localStorage.setItem('auth_token', token);
  else localStorage.removeItem('auth_token');
}

// On app boot: restore from localStorage
authToken = localStorage.getItem('auth_token');
```

### Protected Routes

`<ProtectedRoute>` checks for auth state (Firebase user or stored token). Unauthenticated users are redirected to `/login`.

---

## WebSocket Integration

### Connection Lifecycle

The WebSocket connection is project-scoped. When the user navigates to a project, a WebSocket connection is established. When they leave, it disconnects.

```typescript
// AgentStreamContext manages the connection
const ws = new WebSocketClient(projectId);
ws.connect();  // ws://host/ws?token=...&project_id=...&channels=all

// On project change:
ws.disconnect();
ws = new WebSocketClient(newProjectId);
ws.connect();
```

### Reconnection

Exponential backoff with max 5 attempts:

| Attempt | Delay |
|---------|-------|
| 1 | 1s |
| 2 | 2s |
| 3 | 4s |
| 4 | 8s |
| 5 | 16s |

After 5 failures, stop reconnecting. Show "Disconnected" indicator. User can manually reconnect.

### Event Subscription

Components subscribe to specific event types via the `useWebSocket` hook:

```typescript
const { subscribe } = useWebSocket(projectId);

useEffect(() => {
  const unsubscribe = subscribe<AgentMessageData>('agent_message', (data) => {
    // Handle incoming agent message
    setMessages(prev => [...prev, data]);
  });
  return unsubscribe;
}, [subscribe]);
```

---

## Agent Stream Architecture (NEW)

The agent stream system is the core real-time feature. It replaces the old synchronous chat model.

### How It Works

1. User sends a message to an agent via `POST /api/v1/messages/send`
2. The HTTP response is `202 Accepted` (immediate, no waiting)
3. The agent wakes up and begins processing
4. The backend streams the agent's loop output via WebSocket events:
   - `agent_text`: incremental text output from the LLM
   - `agent_tool_call`: tool call initiated
   - `agent_tool_result`: tool execution result
5. When the agent calls `send_message(target=USER_AGENT_ID, ...)`, an `agent_message` event arrives
6. The frontend displays the stream in real-time

### Stream Buffers

Each agent has an ephemeral stream buffer. Buffers are **not persisted in React state** across component unmounts -- they are transient by design. Historical data is loaded from the API when needed.

```typescript
interface AgentStreamBuffer {
  agentId: string;
  sessionId: string | null;
  chunks: StreamChunk[];         // Rolling buffer, capped at 500 entries
  isStreaming: boolean;
  lastActivity: number;          // timestamp
}

type StreamChunk =
  | { type: 'text'; content: string; timestamp: string }
  | { type: 'tool_call'; toolName: string; toolInput: object; timestamp: string }
  | { type: 'tool_result'; toolName: string; output: string; success: boolean; timestamp: string }
  | { type: 'message'; content: string; from: string; timestamp: string };
```

### AgentStreamContext (NEW)

```typescript
interface AgentStreamContextValue {
  buffers: Map<string, AgentStreamBuffer>;
  inspectedAgentId: string | null;
  setInspectedAgent: (agentId: string) => void;
  getBuffer: (agentId: string) => AgentStreamBuffer;
  clearBuffer: (agentId: string) => void;
}
```

The context:
- Maintains a `Map<agentId, buffer>` of stream buffers
- Listens to `agent_text`, `agent_tool_call`, `agent_tool_result`, and `agent_message` WebSocket events
- Routes events to the correct agent's buffer
- Tracks which agent the user is currently inspecting

---

## Pages

### ProjectsPage (`/repositories`)

Repository list with create and import functionality.

- Lists all repositories owned by the user
- "New Repository" button: name + description → `POST /api/v1/repositories`
- "Import Repository" button: name + GitHub URL → `POST /api/v1/repositories/import`
- Each repo card links to `/repository/{id}/workspace`
- Delete confirmation dialog
- Data: `GET /api/v1/repositories`

### WorkspacePage (`/repository/:projectId/workspace`)

The main workspace. A three-section layout:

```
┌──────────┬──────────────────────────────┬──────────────┐
│          │                              │              │
│ Sidebar  │        Main Content          │   Agents     │
│          │                              │   Panel      │
│ - Logo   │  (varies by active view)     │              │
│ - Repo   │                              │ - Agent list │
│ - Nav    │                              │ - Status     │
│          │                              │ - Actions    │
│          │                              │              │
└──────────┴──────────────────────────────┴──────────────┘
```

**Sidebar** (left, 256px):
- Logo + app name
- Repository selector dropdown
- Navigation links (Chat, Kanban, Workflow, Artifacts)
- User settings link
- Current user display

**Main Content** (center, flexible):
- Switches based on URL: AgentChat, Kanban, Workflow, Artifacts

**Agents Panel** (right, collapsible, 320px):
- Roster of all agents in the project
- Each agent shows: name, role icon, status indicator, current task
- Click an agent to open the Agent Inspector or switch chat target
- Hidden on Workflow view (workflow has its own inspector panel)

### SettingsPage (`/repository/:projectId/settings`)

Project configuration:
- `max_engineers`: slider or number input (1-10)
- `persistent_sandbox_count`: slider or number input (0-5)
- Data: `GET/PATCH /api/v1/repositories/{id}/settings`

### UserSettingsPage (`/settings`)

User profile:
- Display name
- GitHub Personal Access Token (masked input) — per-user setting for repo operations (not used for login)
- Data: `GET/PATCH /api/v1/auth/me`

---

## Components

### AgentChat (NEW -- replaces Chat)

The primary interaction surface. Unlike the old chat which was a fixed user↔GM conversation, AgentChat lets the user message **any agent**.

#### AgentChatView

The main chat container. Renders differently based on context:

```typescript
interface AgentChatViewProps {
  projectId: string;
  targetAgentId?: string;    // If set, chat is scoped to this agent
}
```

Layout:
```
┌──────────────────────────────────────────────┐
│ [Agent Selector: GM ▼]          [Inspector ⚙] │
├──────────────────────────────────────────────┤
│                                              │
│  Agent Stream (live output)                  │
│  ┌────────────────────────────────────────┐  │
│  │ 💭 Thinking: analyzing requirements...│  │
│  │ 🔧 Tool: create_task("Login page")    │  │
│  │ ✅ Task created (id: abc-123)         │  │
│  │ 📨 "I've created a task for the       │  │
│  │     login page and assigned it to      │  │
│  │     Engineer-1."                       │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  Message History                             │
│  ┌────────────────────────────────────────┐  │
│  │ You: Build a login page with OAuth    │  │
│  │ GM: I've created a task for the       │  │
│  │     login page...                     │  │
│  │ You: What's the status?               │  │
│  │ GM: Engineer-1 is implementing it...  │  │
│  └────────────────────────────────────────┘  │
│                                              │
├──────────────────────────────────────────────┤
│ [Type a message to GM...]           [Send ▶] │
└──────────────────────────────────────────────┘
```

**Agent Selector**: dropdown listing all agents (GM, CTO, Engineer-1, etc.). Changing the selection:
- Switches the target for new messages
- Loads message history for the selected agent
- Switches the stream buffer to the selected agent

**Stream vs Messages**: the view has two sections:
1. **Agent Stream** (top): live output from the agent's current session. Shows text chunks, tool calls, and tool results in real-time. Ephemeral -- cleared when the session ends or the user switches agents.
2. **Message History** (bottom): persisted messages between the user and the selected agent, loaded from the API. Scrollable with infinite scroll (paginated).

**Visibility Levels** (toggle in the agent selector area):
- **Default**: show only text output and messages to user
- **Tool calls**: also show tool names and inputs
- **Full debug**: show complete tool inputs/outputs, prompt blocks (power users)

#### MessageInput

```typescript
interface MessageInputProps {
  targetAgentId: string;
  projectId: string;
  onSend: (content: string) => void;
  disabled?: boolean;
}
```

- Text input with submit on Enter (Shift+Enter for newline)
- Send button
- Disabled while sending (debounce)
- Calls `POST /api/v1/messages/send` on submit

#### AgentStream (NEW)

Renders the live stream buffer for the currently inspected agent.

```typescript
interface AgentStreamProps {
  agentId: string;
  visibilityLevel: 'default' | 'tools' | 'debug';
}
```

Rendering rules:
- `text` chunks: render as markdown, append incrementally
- `tool_call` chunks: render as a collapsible card (tool name + input)
- `tool_result` chunks: append result to the matching tool_call card
- `message` chunks (to user): render as a highlighted message bubble
- Auto-scroll to bottom as new chunks arrive
- "Streaming..." indicator when `isStreaming` is true

### AgentsPanel

The right sidebar showing all agents in the project.

```typescript
interface AgentsPanelProps {
  projectId: string;
  onAgentSelect?: (agentId: string) => void;
  selectedAgentId?: string;
}
```

Each agent card shows:
- Role icon (crown for GM, wrench for CTO, code brackets for Engineer)
- Display name
- Status dot: green (active), yellow (busy), gray (sleeping)
- Current task title (if busy)
- Actions: "Message", "Inspect", "Interrupt" (for GM/CTO on active engineers)

Data: `GET /api/v1/agents/status?project_id={uuid}` with polling fallback (every 5s) + WebSocket `agent_status` events for real-time updates.

### AgentInspector

Deep inspection view for a single agent. Shows what the agent is doing in detail.

```typescript
interface AgentInspectorProps {
  agentId: string | null;
}
```

Sections:
1. **Identity**: role, model, status
2. **Working Memory**: the agent's Layer 1 memory content (from `GET /api/v1/agents/{id}/memory`)
3. **Current Session**: if active -- iteration count, elapsed time, current task
4. **Stream**: live output (same as AgentStream but in a compact panel)
5. **Available Tools**: list of tools the agent can call
6. **Session History**: past sessions with end reasons (from `GET /api/v1/sessions`)

### KanbanBoard

Drag-and-drop task board using @dnd-kit.

Columns: `backlog` → `specifying` → `assigned` → `in_progress` → `review` → `done`

Each task card shows:
- Title
- Priority (critical/urgent badges)
- Assigned agent (avatar + name)
- Git branch / PR link (if available)
- Subtask count

Actions:
- Drag between columns to update status
- Click card to open TaskModal (details + edit)
- "New Task" button opens CreateTaskModal
- Delete task (confirmation dialog)

Data flow:
- Initial load: `GET /api/v1/tasks?project_id={uuid}`
- Status change (drag): `PATCH /api/v1/tasks/{id}/status?status={new_status}`
- Real-time updates: WebSocket `task_created` and `task_update` events

### WorkflowGraph

Agent topology visualization using @xyflow/react + dagre for auto-layout.

Nodes represent agents. Edges represent communication channels (who can message whom).

```
┌─────┐     ┌─────┐     ┌────────────┐
│ GM  │────▶│ CTO │     │ Engineer-1 │
│     │◀────│     │◀───▶│            │
└──┬──┘     └─────┘     └────────────┘
   │                     ┌────────────┐
   └────────────────────▶│ Engineer-2 │
                         └────────────┘
```

Node visual encoding:
- Color: green (active), yellow (busy), gray (sleeping)
- Border: pulsing animation when agent is streaming output
- Badge: current task name
- Size: GM and CTO larger than engineers

Clicking a node:
- Selects the agent for the inspector panel
- Shows the agent's stream in the activity feed

Layout alongside:
- Left (60%): Workflow graph
- Right (40%): Activity feed (top half) + Agent Inspector (bottom half)

### ActivityFeed

Scrollable log of agent activity. Shows events from all agents in the project.

```typescript
interface ActivityFeedProps {
  logs: ActivityLogEntry[];
}

interface ActivityLogEntry {
  id: string;
  agentId: string;
  agentRole: string;
  logType: 'thought' | 'tool_call' | 'tool_result' | 'message' | 'error';
  content: string;
  toolName?: string;
  timestamp: string;
}
```

Rendering:
- Each entry shows: agent name (color-coded by role), timestamp, content
- `thought`: italic text
- `tool_call`: monospace, indented
- `tool_result`: monospace, indented, green (success) or red (error)
- `message`: quoted block
- Auto-scroll with a "Jump to latest" button when scrolled up
- Rolling buffer: max 200 entries (oldest dropped)

---

## API Client (`api/client.ts`)

### REST Client

All API calls go through a centralized `request()` function that handles:

- Base URL resolution (`/api/v1`)
- Auth header injection (`Authorization: Bearer <token>`)
- Timeout with `AbortController` (default 10s, configurable)
- Error parsing into `APIClientError` with status, type, and message
- 204 No Content handling

```typescript
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  timeoutMs?: number
): Promise<T>
```

### API Methods (NEW/Changed)

```typescript
// Messages (NEW - replaces chat)
// sendMessage: request body is { project_id, target_agent_id, content } (matches backend POST /api/v1/messages/send)
async function sendMessage(projectId: string, targetAgentId: string, content: string): Promise<ChannelMessage>
async function getMessages(projectId: string, agentId: string, limit?: number, offset?: number): Promise<ChannelMessage[]>
async function getAllMessages(projectId: string, limit?: number, offset?: number): Promise<ChannelMessage[]>

// Agent actions (NEW)
async function interruptAgent(agentId: string, reason: string): Promise<void>
async function wakeAgent(agentId: string, message?: string): Promise<void>
async function getAgentMemory(agentId: string): Promise<{ memory: object | null }>

// Sessions (NEW - replaces jobs)
async function getSessions(projectId: string, agentId?: string, limit?: number, offset?: number): Promise<AgentSession[]>
async function getSession(sessionId: string): Promise<AgentSession>
async function getSessionMessages(sessionId: string, limit?: number, offset?: number): Promise<AgentMessage[]>

// Project settings (NEW)
async function getProjectSettings(projectId: string): Promise<ProjectSettings>
async function updateProjectSettings(projectId: string, data: Partial<ProjectSettings>): Promise<ProjectSettings>

// Existing (unchanged)
async function getRepositories(): Promise<Repository[]>
async function createRepository(data: RepositoryCreate): Promise<Repository>
async function importRepository(data: RepositoryImport): Promise<Repository>
async function getTasks(projectId: string, status?: string): Promise<Task[]>
async function createTask(projectId: string, task: TaskCreate): Promise<Task>
async function updateTask(taskId: string, update: TaskUpdate): Promise<Task>
async function getAgents(projectId: string): Promise<Agent[]>
async function getAgentStatuses(projectId: string): Promise<AgentStatusDetailed[]>
async function getAgentContext(agentId: string): Promise<AgentContext>

// Dropped
// getChatHistory, sendChatMessage (replaced by message API)
// getTickets, createTicket, replyToTicket, closeTicket (tickets deprecated)
```

### WebSocket Client

```typescript
class WebSocketClient {
  constructor(projectId: string)
  connect(): void
  disconnect(): void
  subscribe(handler: (event: WSEvent) => void): () => void
  send(message: unknown): void
  get isConnected(): boolean
}
```

---

## TypeScript Types (`types/index.ts`)

### New Types (additions to existing)

```typescript
// Agent (updated - removes priority, adds memory, updates roles)
interface Agent {
  id: UUID;
  project_id: UUID;
  role: 'manager' | 'cto' | 'engineer';  // removed 'gm', 'om'
  display_name: string;
  model: string;
  status: 'sleeping' | 'active' | 'busy';
  current_task_id: UUID | null;
  sandbox_id: string | null;
  sandbox_persist: boolean;
  memory: object | null;                   // NEW
  created_at: string;
  updated_at: string;
}

// AgentStatusDetailed (extends Agent; used by getAgentStatuses)
interface AgentStatusDetailed extends Agent {
  queue_size: number;
  pending_message_count: number;           // unread channel messages for this agent (replaces open_ticket_count)
  task_queue: TaskSummary[];
}

interface TaskSummary {
  id: UUID;
  title: string;
  status: TaskStatus;
  critical: number;
  urgent: number;
  module_path: string | null;
  updated_at: string;
}

// Task (updated - removes abort fields)
interface Task {
  id: UUID;
  project_id: UUID;
  title: string;
  description: string | null;
  status: TaskStatus;
  critical: number;
  urgent: number;
  assigned_agent_id: UUID | null;
  module_path: string | null;
  git_branch: string | null;
  pr_url: string | null;
  parent_task_id: UUID | null;
  created_by_id: UUID | null;
  created_at: string;
  updated_at: string;
}

// Channel Message (NEW - replaces ChatMessage)
interface ChannelMessage {
  id: UUID;
  project_id: UUID;
  from_agent_id: UUID | null;
  target_agent_id: UUID | null;
  content: string;
  message_type: 'normal' | 'system';
  status: 'sent' | 'received';
  broadcast: boolean;
  created_at: string;
}

// Agent Session (NEW - replaces EngineerJob)
interface AgentSession {
  id: UUID;
  agent_id: UUID;
  project_id: UUID;
  task_id: UUID | null;
  trigger_message_id: UUID | null;
  status: 'running' | 'completed' | 'force_ended' | 'error';
  end_reason: string | null;
  iteration_count: number;
  started_at: string;
  ended_at: string | null;
}

// Agent Message (NEW)
interface AgentMessage {
  id: UUID;
  agent_id: UUID;
  session_id: UUID | null;
  project_id: UUID;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_name: string | null;
  tool_input: object | null;
  tool_output: string | null;
  loop_iteration: number;
  created_at: string;
}

// Project Settings (NEW)
interface ProjectSettings {
  id: UUID;
  project_id: UUID;
  max_engineers: number;
  persistent_sandbox_count: number;
  created_at: string;
  updated_at: string;
}

// Stream chunk types (NEW)
type StreamChunk =
  | { type: 'text'; content: string; agentId: string; timestamp: string }
  | { type: 'tool_call'; toolName: string; toolInput: object; agentId: string; timestamp: string }
  | { type: 'tool_result'; toolName: string; output: string; success: boolean; agentId: string; timestamp: string }
  | { type: 'message'; content: string; fromAgentId: string; timestamp: string };

// WebSocket events (updated)
type WSEventType =
  | 'agent_text'          // NEW: streaming text chunk
  | 'agent_tool_call'     // NEW: tool call initiated
  | 'agent_tool_result'   // NEW: tool result
  | 'agent_message'       // NEW: message to user
  | 'system_message'      // NEW: internal lifecycle (interrupts, status)
  | 'agent_status'
  | 'task_created'
  | 'task_update'
  | 'agent_log'           // Debug activity
  | 'sandbox_log';        // Debug sandbox output

// Dropped types:
// ChatMessage, ChatRole, ChatMessageCreate, SendChatMessageResponse
// Ticket, TicketMessage, TicketType, TicketStatus, TicketCreate, TicketEventData
// JobEventData (replaced by AgentSession)
// AgentRole 'gm' | 'om' variants
```

### Constants

```typescript
const USER_AGENT_ID = '00000000-0000-0000-0000-000000000000';
```

---

## Custom Hooks

### useMessages (NEW)

Manages message history between the user and a specific agent.

```typescript
function useMessages(projectId: string, agentId: string) {
  return {
    messages: ChannelMessage[],
    isLoading: boolean,
    error: string | null,
    sendMessage: (content: string) => Promise<void>,
    loadMore: () => Promise<void>,        // Infinite scroll pagination
    hasMore: boolean,
  };
}
```

Implementation:
- Initial load: `GET /api/v1/messages?project_id=...&agent_id=...`
- Send: `POST /api/v1/messages/send` (fire-and-forget, 202)
- Real-time: subscribes to `agent_message` WebSocket events, appends incoming messages to the list
- Pagination: offset-based, loads older messages on scroll-up

### useAgentStream (NEW)

Manages the live stream buffer for the currently inspected agent.

```typescript
function useAgentStream(projectId: string, agentId: string | null) {
  return {
    chunks: StreamChunk[],
    isStreaming: boolean,
    clearBuffer: () => void,
  };
}
```

Implementation:
- Subscribes to `agent_text`, `agent_tool_call`, `agent_tool_result` WebSocket events
- Filters events by `agentId`
- Appends to a rolling buffer (max 500 chunks)
- `isStreaming` is true when receiving events, false after 3s of inactivity

### useAgents (updated)

```typescript
function useAgents(projectId: string | null) {
  return {
    agents: Agent[],
    isLoading: boolean,
    refreshAgents: () => Promise<void>,
  };
}
```

- Polls `GET /api/v1/agents/status` every 5s as a fallback
- Subscribes to `agent_status` WebSocket events for real-time updates
- Merges WebSocket updates into the agent list

### useSessions (NEW)

```typescript
function useSessions(projectId: string, agentId?: string) {
  return {
    sessions: AgentSession[],
    isLoading: boolean,
    loadMore: () => Promise<void>,
    hasMore: boolean,
  };
}
```

### useTasks (unchanged)

Existing hook for Kanban board state. Subscribes to `task_created` and `task_update` WebSocket events.

---

## Data Flow Patterns

### User Sends a Message (end-to-end)

```
1. User types message, clicks Send
2. Frontend: POST /api/v1/messages/send Body: { project_id, target_agent_id: GM_ID, content: "..." }
3. Backend: 202 Accepted (instant)
4. Backend: persists message to channel_messages
5. Backend: pushes notification to GM's worker queue
6. GM wakes up, reads message from DB
7. GM processes message (LLM call + tool calls)
8. Backend streams agent output via WebSocket:
   - agent_text: "I'll create a task for..."
   - agent_tool_call: { tool: "create_task", input: {...} }
   - agent_tool_result: { output: "Task created" }
9. GM calls send_message(target=USER_AGENT_ID, content="Done! I've created...")
10. Backend: agent_message WebSocket event to frontend
11. Frontend: appends message to message history
12. GM calls END, goes to sleep
13. Frontend: streaming stops, agent_status changes to "sleeping"
```

### User Inspects an Agent

```
1. User clicks on Engineer-1 in the Agents Panel
2. Frontend: switches inspected agent to Engineer-1
3. Frontend: loads Engineer-1's message history (GET /api/v1/messages)
4. Frontend: loads Engineer-1's sessions (GET /api/v1/sessions)
5. Frontend: switches stream buffer to Engineer-1
6. If Engineer-1 is active, live output appears in the stream
7. User can send a message to Engineer-1 from the chat input
```

### User Interrupts an Agent

```
1. User clicks "Interrupt" on an active Engineer-1
2. Frontend: POST /api/v1/agents/{id}/interrupt { reason: "user requested" }
3. Backend: sets interrupt flag on Engineer-1's worker
4. Engineer-1's loop checks flag at next iteration boundary
5. Session ends with reason="interrupted"
6. WebSocket: agent_status event (Engineer-1 → sleeping)
7. Frontend: updates agent card status
```

### Real-time Kanban Update

```
1. GM calls create_task tool (or engineer updates task status)
2. Backend: persists task change to DB
3. Backend: emits task_created/task_update WebSocket event
4. Frontend: KanbanBoard receives event, updates board in place
5. No polling needed -- the board is always up to date
```

---

## Visibility Levels

The frontend controls what the user sees. The backend always streams everything.

| Level | Shows | Use Case |
|-------|-------|----------|
| **Default** | Agent text output + messages to user | Normal usage |
| **Tools** | + tool call names and summaries | Monitoring agent actions |
| **Debug** | + full tool inputs/outputs, prompt blocks | Debugging, power users |

Implementation: a toggle in the AgentChatView header. Controlled via component state. Filters which `StreamChunk` types are rendered.

---

## Responsive Design Notes

- **Desktop-first** (primary target: 1280px+ screens)
- Sidebar collapses to icons at <1024px
- Agents Panel hides and becomes a drawer at <1280px
- Kanban columns stack vertically on mobile (but this is a secondary concern)
- Workflow graph is desktop-only (hidden on small screens)

---

## Migration from Current Frontend

### What Changes

| Current | New |
|---------|-----|
| `ChatView` talks to GM only via sync `POST /chat/send` | `AgentChatView` talks to any agent via async `POST /messages/send` |
| Chat response blocks until GM finishes (30-60s) | Message sends instantly (202), response streams via WebSocket |
| `TicketChat` for agent tickets | Dropped. All communication is `send_message` |
| Agent roles: `gm`, `om`, `manager`, `engineer` | Roles: `manager`, `cto`, `engineer` |
| `engineer_jobs` for tracking engineer work | `agent_sessions` for tracking all agent work |
| Workflow graph shows LangGraph execution | Workflow graph shows agent topology + status |
| `chat_messages` API for history | `messages` API for all agent conversations |

### Migration Steps

1. Update `types/index.ts`: new types, drop deprecated ones
2. Replace `api/client.ts` methods: new message/session/settings endpoints
3. Create new contexts: `ProjectContext`, `AgentStreamContext`
4. Build `AgentChatView` component (replaces `ChatView`)
5. Build `AgentStream` component (new)
6. Update `AgentsPanel` with new schema (remove `priority`, add `memory`)
7. Update `AgentInspector` to use session API instead of job API
8. Update `KanbanBoard` to use new task schema (no abort fields)
9. Update `WorkflowGraph` nodes: `manager`, `cto`, `engineer` (remove `om`)
10. Remove all ticket-related components and hooks
11. Update routes: `/chat` → `/workspace`, add `/workflow`, `/artifacts`
12. Update WebSocket event subscriptions for new event types
