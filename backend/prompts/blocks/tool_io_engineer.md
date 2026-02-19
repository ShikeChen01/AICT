
Engineer-only tools:
- update_task_status(task_id, status)
  - Input: task_id UUID, status string
  - Output: Task status updated: <task_uuid> -> <status>

- abort_task(reason)
  - Input: reason text
  - Output: Task aborted.

- create_branch(branch_name)
  - Input: branch_name string
  - Output: Branch created: <branch_name>

- create_pull_request(title, description?)
  - Input: title required, optional description
  - Output: PR created: <pr_url>