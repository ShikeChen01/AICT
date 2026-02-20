Tool usage rules:
- Any field named *_id (e.g. target_agent_id, task_id, agent_id, session_id) must be a UUID string. Never put display names in UUID fields.
- END must always be called alone in its own response. Never alongside other tool calls.
- On failure, tools return: Tool '{tool_name}' failed: {error}. Read it and retry with a fixed input.
- Call describe_tool(tool_name) at any time to see the full I/O contract for a tool. Call describe_tool() with no arguments to list all available tools.
- execute_command runs inside your dedicated persistent sandbox. The sandbox state (files, packages, processes) carries over between calls within a session.
- Prefer execute_command over reasoning alone for anything that can be verified or run: file edits, tests, installs, git operations, HTTP requests.
