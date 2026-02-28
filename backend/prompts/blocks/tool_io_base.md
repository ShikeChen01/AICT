Tool usage rules:
- Any field named *_id (e.g. target_agent_id, task_id, agent_id, session_id) must be a UUID string. Never put display names in UUID fields.
- END must always be called alone in its own response. Never alongside other tool calls.
- Tool errors are returned as: [ERROR: CODE] message. Hint: next action. Read the code and hint, then retry with a corrected call.
  Common error codes: INVALID_INPUT (fix parameters), PERMISSION_DENIED (wrong role), NOT_FOUND (bad UUID — re-query), SANDBOX_UNAVAILABLE (call sandbox_start_session first), SANDBOX_TIMEOUT (retry or increase timeout).
- Call describe_tool(tool_name) at any time to see the full I/O contract for a tool. Call describe_tool() with no arguments to list all available tools.
- execute_command runs inside your dedicated persistent sandbox. Use it for all shell work including git operations, file edits, tests, installs, and HTTP requests.
