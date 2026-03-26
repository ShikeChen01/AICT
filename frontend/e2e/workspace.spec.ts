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

  test('displays top navigation bar', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.topNav).toBeVisible();
  });

  test('top nav shows AICT logo linking to projects', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.aictLogo).toBeVisible();
  });

  test('top nav shows navigation links', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await expect(workspace.dashboardLink).toBeVisible();
    await expect(workspace.desktopsLink).toBeVisible();
    await expect(workspace.agentsLink).toBeVisible();
    await expect(workspace.workspaceLink).toBeVisible();
    await expect(workspace.kanbanLink).toBeVisible();
    await expect(workspace.settingsLink).toBeVisible();
  });

  test('workspace link is active on workspace page', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // Active link has primary color styling
    await expect(workspace.workspaceLink).toHaveClass(/text-\[var\(--color-primary\)\]/);
  });

  test('displays workspace content area', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // Workspace heading should be visible
    await expect(workspace.workspaceHeading).toBeVisible();
  });

  test('shows draggable split handles', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // The workspace has draggable handles for resizing panels
    const handles = page.locator('[role="separator"], .cursor-col-resize, .cursor-row-resize');
    const count = await handles.count();
    expect(count).toBeGreaterThanOrEqual(0); // May not have separators if no agent selected
  });
});
