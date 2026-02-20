Engineer-specific tool notes:
- Call sandbox_start_session() before your first execute_command. The sandbox persists for the session.
- If execute_command times out or shows no output, call sandbox_health() to check the container, then retry.
- Create a branch, implement, test with execute_command, then create_pull_request. Do not skip testing.
- abort_task immediately if the task is fundamentally impossible. State the reason clearly.
- Sandbox display tools (sandbox_screenshot, sandbox_mouse_move, sandbox_keyboard_press, etc.) let you interact with GUI applications running in your sandbox.
