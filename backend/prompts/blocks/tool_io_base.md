Tool I/O contract (follow exactly):
- General:
  - Any field named *_id (e.g., target_agent_id, task_id, agent_id, session_id) must be a UUID string.
  - Never put display names in UUID fields.
  - On failure, tools return: Tool '{tool_name}' failed: {error}

- end()
  - Input: {}
  - Output: Session ended.

- send_message(target_agent_id, content)
  - Input: target_agent_id=recipient UUID, content=message text
  - Output: Message sent to <target_uuid>

- broadcast_message(content)
  - Input: content=message text
  - Output: Broadcast sent.

- update_memory(content)
  - Input: content=full replacement memory text
  - Output: Memory updated.

- read_history(limit?, offset?, session_id?)
  - Input: optional limit, offset, session_id(UUID)
  - Output: multiple lines like [role] message_content, or No history.

- sleep(duration_seconds)
  - Input: duration_seconds integer (0..3600)
  - Output: Slept for <N> seconds.

- list_tasks(status?)
  - Input: optional status
  - Output: one line per task: <task_id> | [<status>] <title> | assigned=<agent_uuid_or_None>, or No tasks.

- get_task_details(task_id)
  - Input: task_id UUID
  - Output: multiline key/value details (id, title, description, status, assigned_agent_id, git_branch, pr_url)

- execute_command(command, timeout?)         *** PRIMARY TOOL — USE LIBERALLY ***
  - Runs inside your dedicated sandbox container (Ubuntu 22.04, full root access).
  - Input: command string, optional timeout int (default: 120s)
  - Output: command execution text (sandbox ID, exit code, stdout/stderr)
  - The sandbox persists across all execute_command calls in the session — files, installed
    packages, environment variables, and running processes carry over between calls.
  - ALWAYS prefer execute_command over reasoning alone for any task that can be verified,
    computed, or executed: file operations, running scripts, installing packages, compiling
    code, running tests, parsing data, making HTTP requests (curl/wget), git operations, etc.
  - Multi-step workflows: chain commands with && or write a shell script and run it.
  - If a command fails, read stderr carefully, fix the issue, and retry — do not give up after
    one failure.
  - You can install any tool with apt-get / pip / npm; installs persist for the session.
  - Call sandbox_start_session() first if execute_command returns a "sandbox not ready" error.
  - If you see "[command timed out — no output received]": call sandbox_health() to check
    if the container is alive, then retry. Do NOT assume the command ran silently.

- sandbox_start_session()
  - Input: {}
  - Output: sandbox readiness/status text
  - Ensures your sandbox container is running. Call once at the start of sandbox work.
  - TIMING: cold start (new container) takes ~2-3 seconds; idle reuse is ~0.1 seconds.
    The call BLOCKS until the container is healthy — no sleep or polling needed after it returns.
    execute_command, sandbox_health, and sandbox_screenshot are immediately usable.
  - Idempotent — safe to call multiple times.

- sandbox_end_session()
  - Input: {}
  - Output: "Sandbox session ended. Container returned to pool."
  - Releases your sandbox back to the pool. Call when you have finished all sandbox work.

- sandbox_health()
  - Input: {}
  - Output: status=ok|error  uptime=<seconds>s  display=:99
  - TIMING: <0.1s round-trip when the container is healthy.
  - Use to diagnose why execute_command returned no output (container may have crashed).
  - NOT needed as a startup check — sandbox_start_session already waits for readiness.

- list_branches()
  - Input: {}
  - Output: git branch list, or No branches.

- view_diff(base?, head?)
  - Input: optional base/head refs
  - Output: git diff text, or No diff.

- describe_tool(tool_name?)
  - Input: optional tool_name string (omit to list all available tools)
  - Output: detailed description, parameters, and role access for the tool