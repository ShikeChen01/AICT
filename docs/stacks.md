# AICT Technology Stack

## Frontend
- React (SPA)
- WebSocket client for real-time updates (chat, Kanban, activity feed)

## Backend
- Python + FastAPI
- WebSocket server (native FastAPI WebSocket support)

## Database
- PostgreSQL
  - Structured data (projects, agents, tasks, tickets, chat, files)
  - Ticket queue (database-backed, LISTEN/NOTIFY for agent wakeup)
  - pgvector extension for RAG embeddings

## Agent Runtime
- E2B sandboxes
  - One sandbox per agent instance
  - GM / Operation Master: sandbox persists
  - Engineer: sandbox closes when PR merged + no pending tasks

## Agent Models
- GM: Gemini 3 Pro (long context: spec folder + chat history + project knowledge)
- Operation Master: Claude 4.5 Opus (strong tool use, orchestration)
- Engineer L1: Claude 4.5 (cost/performance balance for routine tasks)
- Engineer L2: Claude 4.6 (high capability, token-heavy; hard/critical tasks)

## Git
- Spec folder: Git repo (platform-managed, version history via commits)
- Project code: User's actual Git repo; agents branch → PR → OM merges

## LaTeX
- Containerized pdflatex (Docker with texlive image)

## Authentication
- Single user per instance
- Token-based (API token in env, Bearer auth)

## Real-time Communication
- WebSocket for:
  - Client ↔ GM chat (streamed responses)
  - Kanban board updates
  - Agent activity feed
