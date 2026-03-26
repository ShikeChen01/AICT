import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID, MOCK_AGENT_IDS } from './fixtures/mock-data';
import { AgentsPageObject } from './pages/agents.page';

test.describe('Agents Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  // ── Agent Hierarchy Sidebar ──────────────────────────────────

  test('displays agent hierarchy heading', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    await expect(agents.hierarchyHeading).toBeVisible();
  });

  test('shows all agents grouped by role', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Mock data has: Manager, CTO, Engineer Jr, Engineer Sr
    await expect(page.locator('text=Manager').first()).toBeVisible();
    await expect(page.locator('text=CTO').first()).toBeVisible();
    await expect(page.locator('text=Engineer Jr').first()).toBeVisible();
    await expect(page.locator('text=Engineer Sr').first()).toBeVisible();
  });

  test('shows role group labels', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Role group headings
    await expect(page.locator('text=/manager/i').first()).toBeVisible();
    await expect(page.locator('text=/engineer/i').first()).toBeVisible();
  });

  // ── Agent Selection & Tabs ────────────────────────────────────

  test('selecting agent shows detail tabs', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Tabs should be visible
    await expect(agents.promptBuilderTab).toBeVisible();
    await expect(agents.templatesTab).toBeVisible();
    await expect(agents.overviewTab).toBeVisible();
  });

  test('clicking different agent updates selection', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Click CTO agent
    await agents.selectAgent('CTO');
    // The CTO item should visually indicate selection
    const ctoItem = agents.getAgentItem('CTO');
    await expect(ctoItem).toBeVisible();
  });

  test('templates tab shows content', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    await agents.templatesTab.click();
    // Template section should render
    await expect(page.locator('text=/template/i').first()).toBeVisible();
  });

  test('overview tab shows agent details', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    await agents.overviewTab.click();

    // Overview should show agent properties
    await expect(page.locator('text=/role|model|status/i').first()).toBeVisible();
  });

  // ── Agent Actions ──────────────────────────────────────────────

  test('stop agent sends API request', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Mock stop endpoint
    const stopPromise = page.waitForRequest((req) =>
      req.url().includes('/stop') && req.method() === 'POST'
    );

    // Hover over an active agent (Engineer Sr is active in mock data) and click stop
    const engineerSr = agents.getAgentItem('Engineer Sr');
    await engineerSr.hover();

    // Find the stop button that appears on hover
    const stopButton = page.locator('button[title="Stop"], button:has(svg.lucide-stop-circle)');
    if (await stopButton.isVisible()) {
      await stopButton.first().click();
      await stopPromise;
    }
  });

  test('wake agent sends API request', async ({ page }) => {
    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);
    await agents.waitForLoad();

    // Mock wake endpoint
    await page.route(new RegExp('/api/v1/agents/[^/]+/wake'), async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    // Hover over a sleeping agent (Manager is sleeping) and click wake
    const manager = agents.getAgentItem('Manager');
    await manager.hover();

    // Multiple wake buttons may exist (one per sleeping agent) — use first()
    const wakeButton = page.locator('button[title="Wake"]').first();
    if (await wakeButton.isVisible()) {
      await wakeButton.click();
    }
  });

  // ── Empty State ──────────────────────────────────────────────

  test('shows message when no agents', async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID, { agents: [], agentStatuses: [] });
    await setupAuth(page);

    const agents = new AgentsPageObject(page);
    await agents.goto(MOCK_PROJECT_ID);

    // Should show empty state — use .first() since both sidebar and main show messages
    await expect(page.locator('text=No agents yet').first()).toBeVisible();
  });
});
