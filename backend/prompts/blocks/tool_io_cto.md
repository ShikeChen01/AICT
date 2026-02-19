
CTO-only tools:
- interrupt_agent(target_agent_id, reason)
  - Input: target_agent_id UUID, reason text
  - Output: Interrupted agent <target_uuid>

- spawn_engineer(display_name, seniority?)
  - Input: display_name string (required), optional seniority string (junior/intermediate/senior)
  - Output: Engineer spawned: <engineer_uuid>\n  The engineer is now awake. Send it a message or assign a task to give it work.

- list_agents()
  - Input: {}
  - Output: one line per agent: <agent_uuid> | <display_name> | <role> | <status>

- create_branch(branch_name)
  - Input: branch_name string
  - Output: Branch created: <branch_name>

- create_pull_request(title, description?)
  - Input: title required, optional description
  - Output: PR created: <pr_url>