# MVP-0: Unimplemented Features (High-Level)

A high-level list of what is still left to implement for MVP-0. Features are described at a product/capability level, not implementation detail.

---

## Backend

- **Real E2B sandboxes** — Create and close actual E2B sandboxes via the E2B API; today the service only manages metadata and fake sandbox IDs.
- **Agents hooked to real LLM** — GM (and later OM/Engineers) should call a real model (e.g. Gemini/Claude). Chat currently uses a placeholder GM response.
- **Agent execution in sandboxes** — Run agent loops inside E2B (receive triggers, ensure sandbox, send context, get tool calls, execute tools). Orchestrator today only handles sandbox create/close metadata.
- **Real Git/PR integration** — Branch, commit, push are local git; PR creation returns a local URL. Integrate with a real host (e.g. GitHub/GitLab) for creating and merging PRs where required.
- **Spec and code repo provisioning** — Ensure spec and code repos are cloned/available at the paths used by the file and git services (e.g. on backend start or per project).

---

## Frontend

- **Project management** — List projects and switch the active project. Today the app uses a single hardcoded project ID; no project list or switcher.
- **Agent status and task queue** — Show each agent’s status (busy/idle/active/sleeping) and their task queue. Today only GM “available/busy” is shown in the Chat header; no agents panel or queue view.
- **URL-scoped project** — Route by project (e.g. `/project/:id/chat`, `/project/:id/kanban`) so the active project is clear and bookmarkable.

---

## Integration & Flow

- **End-to-end user → GM flow** — Full path: user message → backend invokes GM (in sandbox or in-process) with real LLM → GM can use tools (tasks, tickets, files, git) → response back to user. Today GM is placeholder and not running in a real sandbox with tools.
- **Ticket/assignment-driven agent wake-up** — When a ticket is created or a task is assigned, wake the target agent (ensure sandbox, optionally invoke). Today ticket creation and task assignment do not trigger real sandbox creation or agent invocation.
- **Engineer and OM execution** — Engineers and OM are not yet invoked in sandboxes with tasks/tickets; only data model and internal APIs exist.

---

## Testing & Quality

- **End-to-end / integration tests** — Automated tests that cover full flows (e.g. create task → assign → agent sees it, or chat → GM response) across backend and optionally frontend.
- **Smoke/verification for deployed app** — Script or checklist to verify the running app (e.g. health, auth, one happy path) in a target environment.

---

*Generated from the MVP-0 implementation plan and current codebase. For implementation order and details, see `.cursor/plans/mvp-0_implementation_496827f7.plan.md` and the “MVP-0 next stage” plan (agent status, project management, LLM).*
