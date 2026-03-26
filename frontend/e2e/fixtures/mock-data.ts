/**
 * Centralized mock data factory for E2E tests.
 * Produces realistic API response objects that match backend Pydantic schemas.
 */

// ── Fixed IDs ────────────────────────────────────────────────────────

export const MOCK_USER_ID = '00000000-0000-0000-0000-000000000001';
export const MOCK_PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
export const MOCK_PROJECT_ID_2 = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
export const MOCK_PROJECT_ID_3 = 'cccccccc-cccc-cccc-cccc-cccccccccccc';

export const MOCK_AGENT_IDS = {
  manager: '11111111-1111-1111-1111-111111111111',
  cto: '22222222-2222-2222-2222-222222222222',
  engineer1: '33333333-3333-3333-3333-333333333333',
  engineer2: '44444444-4444-4444-4444-444444444444',
};

export const MOCK_TASK_IDS = {
  task1: '55555555-5555-5555-5555-555555555555',
  task2: '66666666-6666-6666-6666-666666666666',
  task3: '77777777-7777-7777-7777-777777777777',
};

export const MOCK_MESSAGE_IDS = {
  msg1: '88888888-8888-8888-8888-888888888888',
  msg2: '99999999-9999-9999-9999-999999999999',
};

export const MOCK_SESSION_ID = 'dddddddd-dddd-dddd-dddd-dddddddddddd';
export const MOCK_TEMPLATE_ID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';
export const MOCK_DOCUMENT_ID = 'ffffffff-ffff-ffff-ffff-ffffffffffff';
export const MOCK_SECRET_ID = 'abababab-abab-abab-abab-abababababab';

export const MOCK_SANDBOX_IDS = {
  desktop1: 'dd000001-0000-0000-0000-000000000001',
  desktop2: 'dd000002-0000-0000-0000-000000000002',
};
export const MOCK_SANDBOX_CONFIG_ID = 'cc000001-0000-0000-0000-000000000001';

const NOW = new Date().toISOString();
const YESTERDAY = new Date(Date.now() - 86400000).toISOString();

// ── User ─────────────────────────────────────────────────────────────

export function mockUser(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_USER_ID,
    email: 'e2e-user@example.com',
    display_name: 'E2E User',
    github_token_set: false,
    created_at: YESTERDAY,
    updated_at: NOW,
    ...overrides,
  };
}

// ── Projects / Repositories ──────────────────────────────────────────

export function mockProject(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_PROJECT_ID,
    owner_id: MOCK_USER_ID,
    name: 'Test Repository',
    description: 'A test repository for E2E testing',
    spec_repo_path: '/repos/test-repo/spec',
    code_repo_url: 'https://github.com/test-org/test-repo',
    code_repo_path: '/repos/test-repo/code',
    created_at: YESTERDAY,
    updated_at: NOW,
    ...overrides,
  };
}

export function mockProjects(count = 3) {
  const names = ['Test Repository', 'Frontend App', 'Backend API'];
  const ids = [MOCK_PROJECT_ID, MOCK_PROJECT_ID_2, MOCK_PROJECT_ID_3];
  return Array.from({ length: count }, (_, i) =>
    mockProject({
      id: ids[i] ?? `proj-${i}`,
      name: names[i] ?? `Project ${i + 1}`,
      description: `Description for project ${i + 1}`,
    })
  );
}

// ── Agents ───────────────────────────────────────────────────────────

export function mockAgent(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_AGENT_IDS.manager,
    project_id: MOCK_PROJECT_ID,
    template_id: MOCK_TEMPLATE_ID,
    role: 'manager' as const,
    display_name: 'Manager',
    model: 'claude-sonnet-4-6',
    provider: 'anthropic',
    thinking_enabled: false,
    status: 'sleeping' as const,
    current_task_id: null,
    sandbox_id: null,
    sandbox_persist: false,
    memory: null,
    token_allocations: null,
    created_at: YESTERDAY,
    updated_at: NOW,
    ...overrides,
  };
}

export function mockAgents(projectId = MOCK_PROJECT_ID) {
  return [
    mockAgent({ id: MOCK_AGENT_IDS.manager, project_id: projectId, role: 'manager', display_name: 'Manager' }),
    mockAgent({ id: MOCK_AGENT_IDS.cto, project_id: projectId, role: 'cto', display_name: 'CTO' }),
    mockAgent({ id: MOCK_AGENT_IDS.engineer1, project_id: projectId, role: 'engineer', display_name: 'Engineer Jr', model: 'claude-haiku-4-6' }),
    mockAgent({ id: MOCK_AGENT_IDS.engineer2, project_id: projectId, role: 'engineer', display_name: 'Engineer Sr', model: 'claude-sonnet-4-6', status: 'active' }),
  ];
}

export function mockAgentStatuses(projectId = MOCK_PROJECT_ID) {
  return mockAgents(projectId).map((a) => ({
    ...a,
    queue_size: 0,
    pending_message_count: 0,
    task_queue: [],
  }));
}

// ── Tasks ────────────────────────────────────────────────────────────

export function mockTask(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_TASK_IDS.task1,
    project_id: MOCK_PROJECT_ID,
    title: 'Implement login flow',
    description: 'Add Google OAuth login',
    status: 'backlog' as const,
    critical: 5,
    urgent: 3,
    assigned_agent_id: null,
    module_path: null,
    git_branch: null,
    pr_url: null,
    parent_task_id: null,
    created_by_id: null,
    abort_reason: null,
    abort_documentation: null,
    aborted_by_id: null,
    created_at: YESTERDAY,
    updated_at: NOW,
    ...overrides,
  };
}

export function mockTasks(projectId = MOCK_PROJECT_ID) {
  return [
    mockTask({ id: MOCK_TASK_IDS.task1, project_id: projectId, title: 'Implement login flow', status: 'backlog' }),
    mockTask({ id: MOCK_TASK_IDS.task2, project_id: projectId, title: 'Add user settings', status: 'in_progress', assigned_agent_id: MOCK_AGENT_IDS.engineer1 }),
    mockTask({ id: MOCK_TASK_IDS.task3, project_id: projectId, title: 'Write unit tests', status: 'done' }),
  ];
}

// ── Messages ─────────────────────────────────────────────────────────

export function mockMessage(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_MESSAGE_IDS.msg1,
    project_id: MOCK_PROJECT_ID,
    from_agent_id: null,
    target_agent_id: MOCK_AGENT_IDS.manager,
    from_user_id: MOCK_USER_ID,
    content: 'Hello Manager, please start working on the login feature.',
    message_type: 'normal' as const,
    status: 'sent' as const,
    broadcast: false,
    created_at: NOW,
    attachment_ids: [],
    ...overrides,
  };
}

export function mockMessages(projectId = MOCK_PROJECT_ID, agentId = MOCK_AGENT_IDS.manager) {
  return [
    mockMessage({
      id: MOCK_MESSAGE_IDS.msg1,
      project_id: projectId,
      target_agent_id: agentId,
      from_user_id: MOCK_USER_ID,
      from_agent_id: null,
      content: 'Hello Manager, please start working on the login feature.',
    }),
    mockMessage({
      id: MOCK_MESSAGE_IDS.msg2,
      project_id: projectId,
      from_agent_id: agentId,
      target_agent_id: null,
      from_user_id: null,
      content: 'Understood. I will break this down into tasks and assign engineers.',
    }),
  ];
}

// ── Project Settings ─────────────────────────────────────────────────

export function mockProjectSettings(overrides?: Record<string, unknown>) {
  return {
    id: 'settings-' + MOCK_PROJECT_ID,
    project_id: MOCK_PROJECT_ID,
    max_engineers: 5,
    persistent_sandbox_count: 0,
    model_overrides: null,
    prompt_overrides: null,
    daily_token_budget: 0,
    calls_per_hour_limit: 0,
    tokens_per_hour_limit: 0,
    daily_cost_budget_usd: 0,
    created_at: YESTERDAY,
    updated_at: NOW,
    ...overrides,
  };
}

// ── Project Usage ────────────────────────────────────────────────────

export function mockProjectUsage() {
  return {
    today: {
      date_utc: new Date().toISOString().slice(0, 10),
      total_input_tokens: 125000,
      total_output_tokens: 45000,
      total_tokens: 170000,
      estimated_cost_usd: 1.25,
      by_model: [
        {
          provider: 'anthropic',
          model: 'claude-sonnet-4-6',
          calls: 42,
          input_tokens: 100000,
          output_tokens: 35000,
          estimated_cost_usd: 0.95,
        },
        {
          provider: 'anthropic',
          model: 'claude-haiku-4-6',
          calls: 18,
          input_tokens: 25000,
          output_tokens: 10000,
          estimated_cost_usd: 0.30,
        },
      ],
    },
    last_hour: {
      window: 'last_60_min',
      total_calls: 12,
      total_tokens: 35000,
      by_model: [],
    },
    recent_calls: [
      {
        id: 'call-1',
        provider: 'anthropic',
        model: 'claude-sonnet-4-6',
        input_tokens: 5000,
        output_tokens: 2000,
        total_tokens: 7000,
        estimated_cost_usd: 0.05,
        agent_id: MOCK_AGENT_IDS.manager,
        session_id: MOCK_SESSION_ID,
        created_at: NOW,
      },
    ],
  };
}

// ── Project Secrets ──────────────────────────────────────────────────

export function mockProjectSecrets() {
  return [
    {
      id: MOCK_SECRET_ID,
      name: 'GITHUB_TOKEN',
      hint: 'ghp_',
      created_at: NOW,
    },
    {
      id: 'secret-2',
      name: 'OPENAI_API_KEY',
      hint: 'sk-',
      created_at: NOW,
    },
  ];
}

// ── Sessions ─────────────────────────────────────────────────────────

export function mockSession(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_SESSION_ID,
    agent_id: MOCK_AGENT_IDS.manager,
    project_id: MOCK_PROJECT_ID,
    task_id: null,
    trigger_message_id: null,
    status: 'completed' as const,
    end_reason: 'normal_end' as const,
    iteration_count: 5,
    started_at: YESTERDAY,
    ended_at: NOW,
    ...overrides,
  };
}

// ── Documents ────────────────────────────────────────────────────────

export function mockDocuments() {
  return [
    {
      id: MOCK_DOCUMENT_ID,
      project_id: MOCK_PROJECT_ID,
      doc_type: 'architecture',
      title: 'System Architecture',
      updated_by_agent_id: MOCK_AGENT_IDS.cto,
      updated_by_user_id: null,
      current_version: 2,
      updated_at: NOW,
    },
    {
      id: 'doc-2',
      project_id: MOCK_PROJECT_ID,
      doc_type: 'spec',
      title: 'API Specification',
      updated_by_agent_id: null,
      updated_by_user_id: MOCK_USER_ID,
      current_version: 1,
      updated_at: YESTERDAY,
    },
  ];
}

// ── Templates ────────────────────────────────────────────────────────

export function mockTemplates() {
  return [
    {
      id: MOCK_TEMPLATE_ID,
      project_id: MOCK_PROJECT_ID,
      name: 'Default Manager',
      base_role: 'manager' as const,
      model: 'claude-sonnet-4-6',
      provider: 'anthropic',
      thinking_enabled: false,
      is_system_default: true,
    },
  ];
}

// ── Sandboxes / Desktops ────────────────────────────────────────────

export function mockSandbox(overrides?: Record<string, unknown>) {
  return {
    id: MOCK_SANDBOX_IDS.desktop1,
    user_id: MOCK_USER_ID,
    project_id: MOCK_PROJECT_ID,
    agent_id: null,
    agent_name: null,
    sandbox_config_id: null,
    name: 'Desktop 1',
    description: null,
    orchestrator_sandbox_id: 'orch-unit-001',
    unit_type: 'desktop' as const,
    status: 'idle',
    host: '10.128.0.38',
    port: 9090,
    created_at: YESTERDAY,
    assigned_at: null,
    ...overrides,
  };
}

export function mockDesktops(projectId = MOCK_PROJECT_ID) {
  return [
    mockSandbox({
      id: MOCK_SANDBOX_IDS.desktop1,
      project_id: projectId,
      name: 'Desktop 1',
      orchestrator_sandbox_id: 'orch-unit-001',
      status: 'idle',
    }),
    mockSandbox({
      id: MOCK_SANDBOX_IDS.desktop2,
      project_id: projectId,
      name: 'Desktop 2',
      orchestrator_sandbox_id: 'orch-unit-002',
      status: 'assigned',
      agent_id: MOCK_AGENT_IDS.engineer1,
      agent_name: 'Engineer Jr',
      assigned_at: NOW,
    }),
  ];
}

export function mockSandboxConfigs() {
  return [
    {
      id: MOCK_SANDBOX_CONFIG_ID,
      user_id: MOCK_USER_ID,
      name: 'Default Setup',
      description: 'Standard development environment',
      setup_script: '#!/bin/bash\necho "setup complete"',
      os_image: null,
      created_at: YESTERDAY,
      updated_at: NOW,
    },
  ];
}

export function mockSandboxSnapshots(sandboxId = MOCK_SANDBOX_IDS.desktop1) {
  return [
    {
      id: 'snap-001',
      sandbox_id: sandboxId,
      label: 'Before config change',
      k8s_snapshot_name: 'snap-k8s-001',
      created_at: YESTERDAY,
    },
  ];
}

// ── Billing / Usage ─────────────────────────────────────────────────

export function mockBillingUsage() {
  return {
    headless_seconds_used: 3600,
    headless_seconds_included: 54000,
    desktop_seconds_used: 1800,
    desktop_seconds_included: 54000,
  };
}
