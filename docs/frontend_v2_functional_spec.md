# Frontend V2 Functional Specification & Module List

## Overview
This document outlines the functional requirements for the "Glass Box" frontend update, designed to expose the internal LangGraph workflows, agent interactions, and environment states to the user.

## 1. Live Workflow Graph (The "Brain")

### Functional Requirements
- **Visual Graph:** Render the Directed Acyclic Graph (DAG) corresponding to `backend/graph/workflow.py`.
- **Nodes:** Represent Agents (`Manager`, `OM`, `Engineer`) and Tool Nodes (`manager_tools`, etc.).
- **Edges:** Represent conditional transitions (e.g., `Manager -> OM`, `OM -> Engineer`).
- **Live State:**
  - Highlight the currently active node in real-time.
  - Animate the edge traversed during transitions.
  - Show "Thinking" vs "Idle" states on nodes.
- **Interactivity:**
  - Click a node to open the **Agent Inspector**.
  - Zoom/Pan capabilities.

### Modules & Libraries
- **`@xyflow/react`** (formerly React Flow): Core graph rendering library.
- **`dagre`**: For auto-layout of the graph nodes (hierarchical layout).

---

## 2. Agent Activity Feed (Team Chat)

### Functional Requirements
- **Multi-Agent Log:** A chronological feed of all internal events, distinct from the User-GM chat.
- **Event Types:**
  - **Instructions:** Manager -> OM ("Build feature X").
  - **Tool Use:** "Engineer is reading file `src/app.tsx`".
  - **Tool Output:** "File read successfully (200 lines)".
  - **Errors:** Stack traces or tool failures.
- **Filtering:** Toggle visibility by Agent (Show only Engineer logs) or Level (Info/Debug/Error).
- **Presentation:**
  - Collapsible JSON views for complex tool inputs/outputs.
  - Markdown rendering for text content.

### Modules & Libraries
- **`react-markdown`**: For rendering agent text responses.
- **`react-syntax-highlighter`**: For displaying code blocks and JSON tool outputs.
- **`date-fns`**: For timestamp formatting.

---

## 3. Agent Inspector & Control

### Functional Requirements
- **Inspector Panel:** Slide-over or sidebar panel when an agent is selected.
- **State Visualization:**
  - **System Prompt:** View the static instructions given to the agent.
  - **Short-term Memory:** View the last N messages in the agent's context window.
  - **Tools:** List available tools for this agent.
- **Status Indicators:** Current status (`idle`, `busy`, `awaiting_input`), model name (e.g., `gpt-4o`).

### Modules & Libraries
- **`lucide-react`**: For status icons and UI elements.
- **`framer-motion`**: For smooth panel transitions.

---

## 4. Artifact & Knowledge Browser

### Functional Requirements
- **File Explorer:** Read-only view of the project's file system (mirrored from backend).
- **Artifact Tracking:** Highlight files modified by agents in the current session.
- **Context Viewer:** List documents/specs currently loaded into the agent's context (e.g., "GrandSpecification.tex").
- **Diff Viewer:** Visual diff of changes before they are committed/merged.

### Modules & Libraries
- **`react-diff-view`** or **`diff2html`**: To visualize code changes.
- **`lucide-react`**: File type icons.

---

## 5. Enhanced Kanban (Swimlanes)

### Functional Requirements
- **Swimlane Layout:** Group tasks horizontally by status, vertically by **Assigned Agent**.
- **Drag-and-Drop:**
  - Drag task between columns (Status change).
  - Drag task between swimlanes (Reassign agent - *if backend supported*).
- **Visuals:**
  - distinct avatars for agents.
  - Priority badges (Critical/Urgent).

### Modules & Libraries
- **`@dnd-kit/core`** & **`@dnd-kit/sortable`**: Robust drag-and-drop primitives.
- **`clsx`** / **`tailwind-merge`**: Dynamic class management.

---

## 6. Sandbox & Environment Monitor

### Functional Requirements
- **Environment List:** Show active E2B sandboxes (One per agent or shared).
- **Terminal Stream:** Real-time view of the shell execution (stdout/stderr) from the agent's sandbox.
- **Resource Stats:** (Optional) CPU/RAM usage of the sandbox.

### Modules & Libraries
- **`xterm`**: The standard terminal component for the web.
- **`xterm-addon-fit`**: Auto-resizing for the terminal.

---

## 7. Integrated Git Ops

### Functional Requirements
- **Branch List:** Show active feature branches created by Engineers.
- **PR Dashboard:** List open PRs with status (Open, Merged, Closed).
- **Actions:**
  - "View Diff" (links to Artifact Browser).
  - "Approve/Merge" button (for OM/Human intervention).

### Modules & Libraries
- **`lucide-react`**: Git branch/commit icons.

---

## Summary of New Dependencies

To implement these features, we need to install:

```bash
npm install @xyflow/react dagre react-markdown react-syntax-highlighter date-fns lucide-react framer-motion @dnd-kit/core @dnd-kit/sortable xterm xterm-addon-fit clsx tailwind-merge
```

## Backend Requirements
- **WebSocket Events:**
  - `workflow_update`: Node transitions in the graph.
  - `agent_log`: Internal thought/tool logs.
  - `sandbox_log`: Terminal stdout/stderr.
- **API Endpoints:**
  - `GET /api/v1/artifacts`: List generated files.
  - `GET /api/v1/agents/{id}/context`: Get agent internal state.
