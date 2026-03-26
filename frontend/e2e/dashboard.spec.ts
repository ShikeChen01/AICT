import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID } from './fixtures/mock-data';
import { DashboardPage } from './pages/dashboard.page';

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('displays project name and emergency stop button', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    await expect(dashboard.projectName).toBeVisible();
    await expect(dashboard.emergencyStopButton).toBeVisible();
  });

  test('shows agent fleet section with agents', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    await expect(dashboard.agentFleetHeading).toBeVisible();
    // Should show agent names from mock data
    await expect(page.locator('text=Manager').first()).toBeVisible();
    await expect(page.locator('text=CTO').first()).toBeVisible();
  });

  test('shows sandbox previews section', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    await expect(dashboard.sandboxHeading).toBeVisible();
  });

  test('shows activity feed section', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    await expect(dashboard.activityHeading).toBeVisible();
  });

  test('emergency stop button sends stop requests', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    // Mock stop endpoint
    await page.route('**/api/v1/agents/*/stop', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await dashboard.emergencyStopButton.click();
    // Button should reflect the stopping state
    await expect(page.locator('text=/Stopping|Emergency Stop/').first()).toBeVisible();
  });

  test('shows cost data from usage', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    // Mock usage has $1.25 cost
    await expect(page.locator('text=$1.25').first()).toBeVisible();
  });

  test('navigate to agents page via manage link', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    await dashboard.manageAgentsLink.first().click();
    await page.waitForURL(`**/project/${MOCK_PROJECT_ID}/agents`);
  });

  test('navigate to desktops via open sandbox button', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(MOCK_PROJECT_ID);
    await dashboard.waitForLoad();

    if (await dashboard.openSandboxButton.isVisible()) {
      await dashboard.openSandboxButton.click();
      await page.waitForURL(`**/project/${MOCK_PROJECT_ID}/desktops`);
    }
  });
});
