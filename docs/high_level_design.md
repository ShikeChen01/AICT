# Vibe Coding Canvas — Detailed Product Idea
*Last updated: 2026-01-15*

## 0) One-line pitch
A Miro-like canvas inside VS Code where you model a repo as **Buckets → Modules → Blocks (files)**, then run **recursive agent planning + generation + tests** so every block ships with a passing self-test and every module ships with a composed self-test harness.

---

## 1) Vision and non-goals
### Vision
- **Visual, structured development**: you lay out architecture as draggable entities instead of loose chats.
- **Agent-driven implementation**: agents generate code changes *only for selected scope* with clear constraints.
- **Reproducible outcomes**: every change is diff-first, test-backed, and approval-gated.

### Non-goals (initially)
- Fully autonomous repo-wide refactors without explicit scope selection.
- Long-running E2E suites (keep test time reasonable; CI-friendly).
- Replacing GitHub Issues/PRs (integrate with them instead).

---

## 2) Core objects (data model)
### Entity types
1. **Bucket**
   - Top-level container representing a system boundary (e.g., `backend`, `db`, `infra`, `ml-pipeline`).
   - Buckets **cannot contain buckets**.
   - Bucket defines:
     - External APIs / boundaries
     - Deployment/runtime context
     - Global constraints (language, framework, lint/test tooling)

2. **Module**
   - Logical component; can contain submodules and blocks (infinite depth).
   - Has:
     - Purpose (1–3 sentences)
     - Exports / Imports
     - Dependencies (packages/services)
     - Acceptance criteria
     - Test strategy (module-level harness)

3. **Block**
   - Smallest unit, typically a file.
   - Visual shape encodes block type: `.ts`, `.py`, `.sh`, `.c`, `.md`, etc.
   - Has:
     - File path
     - Purpose (one-sentence)
     - Exports/Imports (symbols, APIs)
     - Constraints (style, patterns, performance)
     - Self-test script (unit/integration as appropriate)

### Relationships
- `contains`: Bucket→Module, Module→(Module|Block)
- `depends_on`: Module↔Module, Block↔Block (import graph)
- `implements`: Block→Requirement/Story (optional)
- `verifies`: TestBlock→Block/Module (optional explicit link)

### Minimal JSON schema (conceptual)
```json
{
  "id": "uuid",
  "type": "bucket|module|block",
  "name": "string",
  "path": "string?",
  "purpose": "string",
  "exports": ["string"],
  "imports": ["string"],
  "deps": ["string"],
  "children": ["uuid"],
  "tests": {
    "block_test": "path?",
    "module_test": "path?"
  },
  "size_hint": "xs|s|m|l|xl",
  "status": "todo|doing|review|done"
}
```

---

## 3) UX: canvas + side panels
### Canvas interactions
- Drag to arrange, connect edges:
  - **Containment edges** (parent/child)
  - **Dependency edges** (imports/exports)
- Zoom, mini-map, multi-select
- Snap-to-grid; auto-layout option (DAG layout)

### Entity panel (right side)
- Name, description, tags
- Exports/Imports editor (autocomplete from repo scan)
- Acceptance criteria checklist
- Test strategy and status
- “Generate / Regenerate / Write tests / Run tests / Create PR” actions

### Action bar (top)
- Scope selector: current selection → module subtree → bucket subtree
- Agent mode: Plan-only / Code+Tests / Tests-only / Refactor
- Guardrails toggles:
  - “No filesystem writes outside selected scope”
  - “No dependency additions without approval”
  - “No network calls” (for tests)

### Kanban (optional view)
- Mirror statuses: todo/doing/review/done
- Sync with GitHub Issues/Projects (two-way where possible)

---

## 4) Repo understanding pipeline (static analysis)
### Inputs
- Workspace filesystem (opened folder)
- Git history + current branch
- Package manifests (package.json/pyproject.toml/requirements.txt, etc.)
- Lint/test config (eslint, prettier, jest, pytest, etc.)
- Language servers where available (TS/JS, Python, etc.)

### Outputs
- File index
- Import graph
- Symbol table (best-effort)
- Suggested module/block purposes (AI summary)
- “Disproportional size” hints (optional)

---

## 5) Agent system: recursive plan → code → tests
### Key principle
**Every block must have a self-test; every module must have a composed self-test harness.**

### Prerequisites (must exist before generation)
- Every entity has a purpose
- Every non-bucket defines exports/imports
- Bucket defines external APIs/boundaries

### Recursive planning algorithm (the “crucial recursion”)
For a selected entity `E` (bucket or module):
1. Draft/refresh **internal flow diagram** for scope.
2. For each child submodule/block: infer/confirm
   - exports/imports, parameter types
   - packages/dependencies
3. Validate lower-level plan aligns with higher-level plan.
   - If misaligned: fix + repeat validation.
4. Produce **implementation stages** (ordered).
5. Emit **immediately implementable blocks** (smallest safe diffs first).
6. Generate **test scripts for all blocks** (unit first; integration as needed).
7. **Recurse into every submodule** and repeat steps 1–6.
8. Generate **module self-test** that runs/aggregates child tests (recursive self-testing).

### Execution loop (diff-first)
- Generate patch (git diff) → run local tests → show results
- User approves → apply patch → commit (optional) → PR (optional)

---

## 6) Testing standards
### Block-level tests
- Must be runnable locally with one command (e.g., `pytest -q`, `npm test`, `pnpm test`)
- Prefer deterministic tests (no external network; mock I/O)
- Time budget: keep individual block tests short

### Module-level tests
- Focus on boundaries and composition:
  - correct imports/exports
  - correct external calls and adapters
- Can be lighter than full E2E

### “Green means done”
- Block considered implemented when its self-test passes.
- Module considered implemented when its module harness passes.

---

## 7) VS Code extension architecture
### Extension components
- **Webview Canvas UI**
  - React/TS front-end (canvas rendering: Konva/Fabric/React Flow)
  - State management (Zustand/Redux)
- **Extension Host (Node)**
  - File scanning + indexing
  - Git operations (via simple-git)
  - Test runner orchestration
  - Agent orchestration (calls to chosen LLM providers)

### Provider integrations (Codex/Claude/etc.)
- Unified adapter interface:
  - `plan(scope, context) -> plan`
  - `generate(scope, plan, constraints) -> patch`
  - `review(patch) -> risks/suggestions`
  - `test(scope) -> results`
- Support multiple “agents”:
  - Planner, Implementer, Tester, Reviewer
- Pluggable model routing (cost/perf policies)

### Terminal access model (safety)
- Default: **no arbitrary shell**; only allow whitelisted commands:
  - tests, format, lint, typecheck
- Escalation: user can grant broader permissions per workspace.

---

## 8) Permissions and guardrails
- Scope-limited writes: only under selected module paths
- Dependency changes require explicit approval
- Secret handling:
  - Never read `.env` unless user opts in
  - Redact known secret patterns in context
- Git safety:
  - Always stash/branch before large patches (optional toggle)

---

## 9) GitHub integration
### Minimal MVP
- Create Issue from entity
- Create branch + commit + PR for a selected scope
- Update status back to Kanban column

### Nice-to-have
- Map Modules ↔ GitHub Project items
- Auto-link PRs to Issues
- Embed test status in entity panel

---

## 10) MVP milestones
### MVP-0 (Canvas + data model)
- Create/edit bucket/module/block
- Persist to `.vibecanvas.json`
- Import basic repo tree into blocks

### MVP-1 (Planning + summaries)
- AI summaries for entities
- Manual exports/imports editing
- Dependency edges

### MVP-2 (Code generation with tests)
- Generate patch for selected blocks
- Autogenerate block tests
- Run tests and show logs

### MVP-3 (Recursive module self-test)
- Generate module harness that composes child tests
- “Green means done” workflow

### MVP-4 (GitHub + PR flow)
- Branch/commit/PR + basic Issue sync

---

## 11) Engineering diagrams to include (docs)
- System context diagram
- Module decomposition tree
- Dependency graph (imports/exports)
- Sequence diagram: “Generate → Patch → Test → Approve → Commit”
- State machine: entity status transitions
- Data flow diagram: repo scan → context → agent prompts → patch
- Threat model (permissions/secrets)

---

## 12) Prompt templates (sketch)
### Planner
- Inputs: selected scope tree, exports/imports, constraints, repo conventions
- Outputs: staged plan + tests checklist + risks

### Implementer
- Inputs: plan stage + relevant files + constraints
- Output: unified diff + rationale + new/updated tests

### Tester
- Inputs: test commands + environment assumptions
- Output: pass/fail + log summary + suggested fixes

### Reviewer
- Inputs: diff + risk policies
- Output: review comments + security/perf flags

---

## Appendix: Current draft (raw)
# Workspace notes

(Use this canvas to capture your high-level ideas. I’ll keep organizing and expanding them as you add more.)

## Current draft

### Vision

- **You** design and rearrange coding blocks on a Miro-like canvas.
- **Agents** generate/refine code for the selected blocks using repo context and constraints.
- **Promise**: keep work structured, reviewable, and reproducible (diff-first, approval-gated).

### Task Manager

- **Bucket**
  - Outmost module
- **Module** (logical component)
  - A container; module within a module is valid
  - UI: name; click lists submodules and blocks with progress bars; option to click them to see an action menu and detailed description
  - User can adjust the size of the module to indicate the size of the work
- **Block** (smallest unit): typically a file; block type controls its visual shape (e.g., `.py`, `.ts`, `.sh`, `.c`).
  - User can also adjust the size, but to a certain limit
- Blocks and modules are entities
- All blocks and modules by default have a small AI-generated one-sentence summary of purpose
- AI notifies if a block or module is disproportional to its size (low priority, optional feature)

**Kanban Board**

I also want a GitHub kanban board linked to this Task Manager — a GitHub Kanban Board would be perfect.

### Agent prompt

#### Prerequisites

- Every **entity** (module or block) has a clear purpose description.
- Every **non-bucket entity** defines:
  - **exports** (what it provides)
  - **imports** (what it depends on)
- Every **bucket** defines its **external APIs** (boundaries to outside systems).

#### Planning stage (applies recursively)

1. Draw/revise the **internal flow diagram** for the current scope.
2. For every **submodule and block**, generate:
   - export members, import members
   - parameter types
   - packages
   - dependencies
3. Verify the **validation plan** matches the upper-level (HL) implementation plan. If misaligned: fix alignment, then **repeat step 3**.
4. Based on entity info, generate **stages of implementation**.
5. Generate **immediately implementable blocks**.
6. Generate **testing scripts for all blocks**.
7. **Recurse into every submodule** and repeat steps 1–7.
8. Generate a **self-test script for the current module** that composes/runs child block tests (recursive self-testing).

#### Execution

User clicks **Generate** in the action bar to start code generation.

#### Testing standard

- If a block’s test script passes, the block is considered successfully implemented.
- Module-level tests can be looser: focus on correct API boundaries/external calls.
- Avoid overly long suites (don’t create “10-hour” tests).

