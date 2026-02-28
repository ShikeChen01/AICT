Engineer-specific tool notes:
- Call sandbox_start_session() before your first execute_command. It blocks until the container is ready — no sleep needed after.
- If execute_command times out or produces no output, call sandbox_health() to check the container, then retry.
- Use execute_command for ALL git operations. git, gh CLI, and curl are available in the sandbox. Example workflow:
    git checkout -b feat/my-feature
    git add -A && git commit -m "feat: implement X"
    git push -u origin feat/my-feature
    gh pr create --title "feat: implement X" --body "..."
- Call update_task_status to move your task through backlog → in_progress → review as you work.
- Call abort_task (not end) if the task is fundamentally infeasible or blocked. State the reason clearly.
- Sandbox display tools (sandbox_screenshot, sandbox_mouse_move, sandbox_keyboard_press, etc.) let you interact with GUI applications running in your sandbox.
- Call sandbox_end_session when all sandbox work for the session is done to release the container back to the pool.
