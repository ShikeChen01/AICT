# Extension Architecture (3-Part Client + Cloud)

This extension is a **large client application** with **no backend** (beyond cloud model APIs). The architecture is intentionally split into **three parts** with hard boundaries.

---

## 1) UI Layer (Webview)
**Purpose:** interactive canvas + chat + approvals.

**Components**
- **Canvas renderer (React Flow):** nodes/edges, drag/connect, hover menus, zoom/minimap
- **Inspector panel:** edit entity metadata (exports/imports, tests, acceptance criteria, status)
- **Agent panel:** conversation, job progress, diff preview, approval prompts
- **UI state store:** Zustand
- **UI ↔ Host RPC client:** typed `postMessage` bridge

**Rules**
- UI does **not** access filesystem, secrets, terminal, or network directly.

---

## 2) Local Controller Layer (VS Code Extension Host)
**Purpose:** the **only** layer allowed to touch the local machine/workspace.

**Core components**
- **Message Router (RPC server):** receives UI requests (`startWork`, `runTests`, `applyPatch`, `repoIndex`, etc.)
- **Workspace Store:** read/write `.vibecanvas.json`, maintain `.vibecanvas.cache.json`
- **Repo Indexer:** file tree, manifests, test command discovery, import graph
- **Policy Engine (Guardrails):** scope fence, command allowlist, network policy, dependency-change gate
- **Patch Engine:** validate unified diff → dry-run apply → (optional) format/lint → apply real
- **Command Runner:** `spawn`-based runner with timeouts, cwd controls, env allowlist, output truncation
- **Network Client:** cloud API calls (agent providers); handles proxy/retries/streaming

**Rules**
- Everything that needs “authorization” is enforced here (because extension host runs with VS Code’s user privileges).

---

## 3) Cloud Agent Gateway Layer (API client + provider adapters)
**Purpose:** talk to **OpenAI / Claude / Gemini** efficiently and safely.

**Components**
- **Gateway client:** streaming, retries, backoff, request IDs, rate-limit handling
- **Provider adapters (3 only):** OpenAI Responses, Claude Messages/SDK, Gemini API/Vertex
- **Context Packager:** Context Bundle under **byte caps + token caps**
- **Batch Planner:** two-phase calls `PLAN → PATCH(stage)`; module-level batching; auto-splitting
- **Output validators:** Plan/Review schema validation + unified-diff validation

**Rules**
- Cloud never receives the full repo; it receives **scoped bundles** and **trimmed logs** only.

---

## The two pipes
1) **Webview ↔ Extension Host:** typed RPC (local boundary)
2) **Extension Host ↔ Cloud:** HTTPS streaming API calls (rate limits, retries)

---

## Minimal folder layout (to keep it sane)
- `src/extension/` → `rpc/`, `policy/`, `patch/`, `runner/`, `repoIndex/`, `storage/`, `cloud/`
- `src/webview/` → `canvas/`, `inspector/`, `agentPanel/`, `store/`, `rpcClient/`
- `src/shared/` → `schemas/` (zod), `types/` (RPC + Job + Plan/Diff)
