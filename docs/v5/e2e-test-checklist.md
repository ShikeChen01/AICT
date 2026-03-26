# E2E Test Checklist

Live environment validation. Test against deployed servers.

---

## VNC / Desktop (Critical Path)

- [ ] **1. Create desktop** — "New Desktop" on `/project/{id}/desktops` provisions successfully
- [ ] **2. MJPEG thumbnail** — grid view shows live-updating thumbnail with green connection dot
- [ ] **3. Expand to VNC** — click desktop card, full VNC canvas loads with "VNC Live" green indicator
- [ ] **4. Desktop environment** — Openbox desktop with taskbar visible (not blank/black screen)
- [ ] **5. Chrome welcome page** — Chrome auto-launches with "Sandbox Ready" welcome
- [ ] **6. Mouse interaction** — click inside VNC canvas, cursor moves on remote desktop
- [ ] **7. Keyboard interaction** — type in terminal or Chrome, keystrokes register
- [ ] **8. Right-click menu** — right-click background shows Terminal / Chrome / File Manager
- [ ] **9. Interactive/View-only toggle** — View Only blocks input; switching back restores it
- [ ] **10. Assign agent** — dropdown assigns agent to desktop, status updates
- [ ] **11. Unassign agent** — detach agent, status returns to idle
- [ ] **12. Restart desktop** — click Restart, desktop comes back with VNC working
- [ ] **13. Destroy desktop** — click Destroy, removed from grid

## Dashboard

- [ ] **14. Dashboard loads** — `/project/{id}/dashboard` shows budget, tokens, agent fleet, activity feed
- [ ] **15. Sandbox thumbnails** — live MJPEG previews of desktops on dashboard
- [ ] **16. Agent fleet cards** — shows role, status, model for each agent
- [ ] **17. Emergency Stop All** — button visible and clickable
- [ ] **18. Navigation links** — "Manage" → agents page, thumbnail → desktops page

## Agents

- [ ] **19. Agent tree** — sidebar shows agents grouped by role (Manager > CTO > Engineers)
- [ ] **20. Status indicators** — colored dots reflect agent state
- [ ] **21. Stop/Wake agent** — hover → stop changes status; wake resumes
- [ ] **22. Prompt Builder tab** — block editor loads, config editable
- [ ] **23. Templates tab** — browse available templates
- [ ] **24. Overview tab** — agent stats (role, model, queue size)

## Workspace / Co-Pilot

- [ ] **25. Workspace layout** — `/project/{id}/workspace` shows VNC + stream + conversation split
- [ ] **26. Agent picker** — dropdown switches agents, VNC/conversation update
- [ ] **27. Send message** — type and send, appears in conversation
- [ ] **28. Agent stream** — live activity logs appear during agent execution
- [ ] **29. Draggable splitters** — horizontal and vertical resize work
- [ ] **30. Co-Pilot page** — `/project/{id}/copilot` loads with larger VNC + sidebar

## Kanban

- [ ] **31. Board loads** — `/project/{id}/kanban` shows columns
- [ ] **32. Task cards** — cards render with content
- [ ] **33. Create task** — "+" → fill modal → task appears in correct column

## Projects

- [ ] **34. Projects list** — `/projects` shows all projects in grid
- [ ] **35. Create project** — modal creates project successfully
- [ ] **36. Navigate to project** — click card → opens workspace
- [ ] **37. Delete project** — confirmation dialog, project removed

## Settings

- [ ] **38. User Settings** — `/settings` shows profile, GitHub PAT, tier badge, billing link
- [ ] **39. API Key Manager** — add/view/delete per-user LLM API keys
- [ ] **40. Project Settings** — `/project/{id}/settings` edit name, budgets, rate limits, secrets
- [ ] **41. Secrets management** — add, delete, .env upload all work
- [ ] **42. Billing page** — `/settings/billing` shows plan, usage bars, upgrade cards

## Auth & Navigation

- [ ] **43. Login** — Google OAuth flow works
- [ ] **44. Sidebar navigation** — all nav links route correctly
- [ ] **45. Protected routes** — unauthenticated access redirects to login
