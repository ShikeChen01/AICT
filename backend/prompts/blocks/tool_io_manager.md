Manager-specific tool notes:
- spawn_engineer then send_message to give the engineer its first task.
- assign_task sets the task's assigned_agent_id. The engineer still needs a send_message to wake them.
- interrupt_agent force-ends another agent's current session. Use sparingly.
- remove_agent permanently removes an engineer from the project. This cannot be undone.
