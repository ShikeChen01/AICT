
CTO-only tools:
- interrupt_agent(target_agent_id, reason)
  - Input: target_agent_id UUID, reason text
  - Output: Interrupted agent <target_uuid>

- list_agents()
  - Input: {}
  - Output: one line per agent: <agent_uuid> | <display_name> | <role> | <status>

- create_branch(branch_name)
  - Input: branch_name string
  - Output: Branch created: <branch_name>

- create_pull_request(title, description?)
  - Input: title required, optional description
  - Output: PR created: <pr_url>