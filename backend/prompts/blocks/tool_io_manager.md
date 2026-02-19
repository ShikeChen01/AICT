
Manager-only tools:
- interrupt_agent(target_agent_id, reason)
  - Input: target_agent_id UUID, reason text
  - Output: Interrupted agent <target_uuid>

- spawn_engineer(display_name, seniority?)
  - Input: display_name string (required), optional seniority string (junior/intermediate/senior)
  - Output: Engineer spawned: <engineer_uuid>\n  The engineer is now awake. Send it a message or assign a task to give it work.

- list_agents()
  - Input: {}
  - Output: one line per agent: <agent_uuid> | <display_name> | <role> | <status>

- create_task(title, description?, critical?, urgent?)
  - Input: title required, optional description, critical, urgent
  - Output: Task created: <task_uuid>

- assign_task(task_id, agent_id)
  - Input: task_id UUID, agent_id UUID
  - Output: Task assigned: <task_uuid> -> <agent_uuid>

- update_task_status(task_id, status)
  - Input: task_id UUID, status string
  - Output: Task status updated: <task_uuid> -> <status>