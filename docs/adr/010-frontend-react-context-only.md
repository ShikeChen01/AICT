# ADR-010: Frontend State with React Context Only

## Status

Accepted

## Context

The AICT frontend is a React SPA that manages several types of state:
- **Auth state** — Firebase user, token
- **Project state** — active project, project list
- **Agent state** — agent list, status, inspected agent
- **Stream state** — per-agent WebSocket stream buffers
- **Task state** — Kanban board items
- **Message state** — conversation history per agent

Options for state management:
1. **Redux** — industry standard, but heavy boilerplate, overkill for this app's complexity.
2. **Zustand / Jotai / Recoil** — lighter alternatives, but add a dependency for what React can handle natively.
3. **React hooks + context only** — no external library. Context for global concerns, hooks for feature-specific state.

## Decision

**React hooks + context only. No external state management library.**

Architecture:
- **Context providers** (`AuthProvider`, `ProjectProvider`, `AgentStreamProvider`) for global state that many components need.
- **Custom hooks** (`useAgents`, `useMessages`, `useAgentStream`, `useSessions`, `useTasks`) for feature-specific state.
- **Component-local state** for UI concerns (modals, selections, input values).
- **WebSocket event handlers** for real-time updates (push, not poll).
- **API calls** for initial data loads and user actions.

Key design choice: **stream buffers are ephemeral.** Agent output is held in a rolling buffer (capped at 500 entries) per agent, not permanently stored in React state. Historical data loads from the API on demand.

## Consequences

**Positive:**
- No external dependency to learn, maintain, or version-bump.
- React 19's improvements to context performance make this viable even with frequent updates.
- The state model is simple: context for "what project am I in?" and "what agent am I inspecting?", hooks for "load this data" and "subscribe to these events".
- Stream buffers as ephemeral data avoids unbounded memory growth from long-running agent sessions.

**Negative:**
- Context re-renders can cause performance issues if not carefully structured. Mitigated by: splitting context by concern (auth, project, stream are separate providers), and using `useMemo`/`useCallback` in providers.
- No built-in devtools (unlike Redux DevTools). Debugging state issues requires console logging or React DevTools.
- If the app grows significantly in complexity (e.g., multi-tab support, offline mode), a state library may become necessary.

**Trade-off accepted:**
- The simplicity of no external library outweighs the devtools and middleware benefits of Redux/Zustand for an app of this complexity.
