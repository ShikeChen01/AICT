import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID } from './fixtures/mock-data';
import { WorkspacePage } from './pages/workspace.page';

test.describe('Top Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('navigates to dashboard', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.dashboardLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/dashboard`));
  });

  test('navigates to desktops', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.desktopsLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/desktops`));
  });

  test('navigates to agents', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.agentsLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/agents`));
  });

  test('navigates to workspace', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    // Start on dashboard
    await page.goto(`/project/${MOCK_PROJECT_ID}/dashboard`);
    await workspace.waitForLoad();

    await workspace.workspaceLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/workspace`));
  });

  test('navigates to kanban', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.kanbanLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/kanban`));
  });

  test('navigates to settings', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.settingsLink.click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/settings`));
  });

  test('AICT logo links to projects', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.aictLogo.click();
    await expect(page).toHaveURL(/\/projects$/);
  });
});
