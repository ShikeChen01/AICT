import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID } from './fixtures/mock-data';
import { WorkspacePage } from './pages/workspace.page';

test.describe('Workspace Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('displays workspace layout with sidebar and main content', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.sidebar).toBeVisible();
    await expect(workspace.mainContent).toBeVisible();
  });

  test('sidebar shows project selector with projects', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.projectSelector).toBeVisible();
  });

  test('sidebar shows AICT branding', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.aictLogo).toBeVisible();
    await expect(page.getByText(/agent monitoring console/i)).toBeVisible();
  });

  test('sidebar navigation links are present', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.workspaceLink).toBeVisible();
    await expect(workspace.kanbanLink).toBeVisible();
    await expect(workspace.promptAssemblyLink).toBeVisible();
    await expect(workspace.architectureLink).toBeVisible();
    await expect(workspace.settingsLink).toBeVisible();
    await expect(workspace.aiUsageLink).toBeVisible();
  });

  test('user settings link is in sidebar footer', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.userSettingsLink).toBeVisible();
  });

  test('displays monitoring panels in workspace view', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.liveStreamPanel).toBeVisible();
    await expect(workspace.agentsPanel).toBeVisible();
    await expect(workspace.activityTimeline).toBeVisible();
  });

  test('shows resizable panel separators', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    const separators = page.locator('[role="separator"]');
    await expect(separators.first()).toBeVisible();
  });

  test('workspace link is active when on workspace view', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // Active link should have the active styling class
    await expect(workspace.workspaceLink).toHaveClass(/bg-white/);
  });
});
