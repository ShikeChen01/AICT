# Architecture Decision Records

This directory contains the Architecture Decision Records (ADRs) for AICT. Each ADR captures a significant architectural decision, its context, the decision itself, and its consequences.

## Format

Each ADR follows the [Michael Nygard template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
- **Status** — Proposed, Accepted, Deprecated, Superseded
- **Context** — What situation prompted this decision?
- **Decision** — What did we decide?
- **Consequences** — What are the trade-offs?

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-postgresql-single-source-of-truth.md) | PostgreSQL as single source of truth | Accepted |
| [002](002-universal-agent-execution-loop.md) | Universal agent execution loop | Accepted |
| [003](003-channel-messages-unified-communication.md) | Channel messages as unified communication | Accepted |
| [004](004-in-process-async-workers.md) | In-process async workers | Accepted |
| [005](005-provider-agnostic-llm-layer.md) | Provider-agnostic LLM layer | Accepted |
| [006](006-platform-not-workflow.md) | Platform, not workflow | Accepted |
| [007](007-self-healing-reconciler.md) | Self-healing Reconciler | Accepted |
| [008](008-firebase-auth-separate-github-credentials.md) | Firebase auth with separate GitHub credentials | Accepted |
| [009](009-ephemeral-vs-persistent-sandboxes.md) | Ephemeral vs. persistent sandboxes | Accepted |
| [010](010-frontend-react-context-only.md) | Frontend: React context only | Accepted |

## Adding a New ADR

1. Create a new file: `NNN-short-title.md` (three-digit zero-padded number)
2. Use the template above (Status, Context, Decision, Consequences)
3. Add an entry to this index
4. Update the ADR table in [arc42-lite.md](../arc42-lite.md) section 9
