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

- execute_command(command, timeout?)
  - Input: command string, optional timeout int
  - Output: command execution text (sandbox status, exit code, stdout/stderr)

- start_sandbox()
  - Input: {}
  - Output: sandbox readiness/status text

- list_branches()
  - Input: {}
  - Output: git branch list, or No branches.

- view_diff(base?, head?)
  - Input: optional base/head refs
  - Output: git diff text, or No diff.