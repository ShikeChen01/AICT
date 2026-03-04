/**
 * Reusable API route mock helpers for E2E tests.
 * Uses page.route() to intercept HTTP requests — no backend required.
 */

import { Page } from '@playwright/test';
import {
  mockUser,
  mockProjects,
  mockProject,
  mockAgents,
  mockAgentStatuses,
  mockTasks,
  mockMessages,
  mockProjectSettings,
  mockProjectUsage,
  mockProjectSecrets,
  mockDocuments,
  mockTemplates,
  mockSession,
  MOCK_PROJECT_ID,
} from './mock-data';

export interface AuthMockOptions {
  user?: Record<string, unknown>;
  projects?: Record<string, unknown>[];
}

export interface ProjectMockOptions {
  agents?: Record<string, unknown>[];
  agentStatuses?: Record<string, unknown>[];
  tasks?: Record<string, unknown>[];
  messages?: Record<string, unknown>[];
  settings?: Record<string, unknown>;
  usage?: Record<string, unknown> | null;
  secrets?: Record<string, unknown>[];
  documents?: Record<string, unknown>[];
  templates?: Record<string, unknown>[];
  sessions?: Record<string, unknown>[];
}

/**
 * Mock authentication + top-level API endpoints.
 */
export async function mockAuthenticatedAPIs(
  page: Page,
  options: AuthMockOptions = {}
) {
  const user = options.user ?? mockUser();
  const projects = options.projects ?? mockProjects();

  await page.route('**/api/v1/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    });
  });

  await page.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...user, ...route.request().postDataJSON() }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(user),
      });
    }
  });

  await page.route('**/api/v1/repositories', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(mockProject({ ...body, id: 'new-project-id' })),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(projects),
      });
    }
  });

  await page.route('**/api/v1/repositories/import', async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(mockProject({ ...body, id: 'imported-project-id' })),
    });
  });
}

/**
 * Mock all project-scoped API endpoints.
 */
export async function mockProjectAPIs(
  page: Page,
  projectId = MOCK_PROJECT_ID,
  options: ProjectMockOptions = {}
) {
  const agents = options.agents ?? mockAgents(projectId);
  const agentStatuses = options.agentStatuses ?? mockAgentStatuses(projectId);
  const tasks = options.tasks ?? mockTasks(projectId);
  const allMessages = options.messages ?? mockMessages(projectId);
  const settings = options.settings ?? mockProjectSettings({ project_id: projectId });
  const usage = options.usage === undefined ? mockProjectUsage() : options.usage;
  const secrets = options.secrets ?? mockProjectSecrets();
  const documents = options.documents ?? mockDocuments();
  const templates = options.templates ?? mockTemplates();
  const sessions = options.sessions ?? [mockSession({ project_id: projectId })];

  // GET /repositories/:id
  await page.route(`**/api/v1/repositories/${projectId}`, async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    } else if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockProject({ id: projectId, ...body })),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockProject({ id: projectId })),
      });
    }
  });

  // Agents
  await page.route(`**/api/v1/agents/status?project_id=${projectId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agentStatuses),
    });
  });

  await page.route(new RegExp(`/api/v1/agents\\?project_id=${projectId}`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
    });
  });

  // Tasks
  await page.route(new RegExp(`/api/v1/tasks\\?project_id=${projectId}`), async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ ...tasks[0], ...body, id: 'new-task-id' }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(tasks),
      });
    }
  });

  // Messages
  await page.route(new RegExp(`/api/v1/messages/all\\?project_id=${projectId}`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(allMessages),
    });
  });

  await page.route(new RegExp(`/api/v1/messages\\?project_id=${projectId}`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(allMessages),
    });
  });

  await page.route('**/api/v1/messages/send', async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(mockMessages()[0]),
    });
  });

  // Settings
  await page.route(`**/api/v1/repositories/${projectId}/settings`, async (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...settings, ...body }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(settings),
      });
    }
  });

  // Usage
  await page.route(`**/api/v1/repositories/${projectId}/usage`, async (route) => {
    if (usage === null) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(usage),
      });
    }
  });

  // Secrets
  await page.route(new RegExp(`/api/v1/repositories/${projectId}/secrets(/.*)?$`), async (route) => {
    const method = route.request().method();
    if (method === 'DELETE') {
      await route.fulfill({ status: 204 });
    } else if (method === 'POST' || method === 'PUT') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'new-secret-id',
          name: body.name,
          hint: body.value?.slice(-4) ?? null,
          created_at: new Date().toISOString(),
        }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(secrets),
      });
    }
  });

  // Documents
  await page.route(`**/api/v1/repositories/${projectId}/documents`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(documents),
    });
  });

  // Templates
  await page.route(new RegExp(`/api/v1/templates/projects/${projectId}/templates`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(templates),
    });
  });

  // Sessions
  await page.route(new RegExp(`/api/v1/sessions\\?project_id=${projectId}`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(sessions),
    });
  });

  // Prompt blocks (catch-all for any agent)
  await page.route(new RegExp(`/api/v1/prompt-blocks/agents/.+/blocks`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Tool configs (catch-all for any agent)
  await page.route(new RegExp(`/api/v1/tool-configs/agents/.+/tools`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });
}

/**
 * Convenience: set up both auth and project mocks in one call.
 */
export async function mockWorkspaceAPIs(
  page: Page,
  projectId = MOCK_PROJECT_ID,
  options: AuthMockOptions & ProjectMockOptions = {}
) {
  await mockAuthenticatedAPIs(page, options);
  await mockProjectAPIs(page, projectId, options);
}
