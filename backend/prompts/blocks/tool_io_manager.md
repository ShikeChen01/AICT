Manager-specific tool notes:
- Call get_project_metadata at session start to orient yourself to project state (agents, tasks, repo).
- Call list_agents to discover agent UUIDs before send_message, assign_task, interrupt_agent, or remove_agent.
- Task workflow: create_task → assign_task (sets assigned_agent_id) → send_message to wake the engineer.
- update_task_status lets you update any task regardless of who it is assigned to.
- interrupt_agent force-ends another agent's current session. Use when an agent is stuck or priorities have changed.
- remove_agent permanently removes an engineer: their worker, sandbox, sessions, and history are fully deleted. Tasks reset to backlog. Cannot be undone.
- Use broadcast_message for team-wide announcements; prefer send_message for targeted 1-on-1 communication.
