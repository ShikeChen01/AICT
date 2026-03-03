import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import {
  MOCK_PROJECT_ID,
  MOCK_PROJECT_ID_2,
  mockProjects,
} from './fixtures/mock-data';
import { WorkspacePage } from './pages/workspace.page';

test.describe('Sidebar Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID, {
      projects: mockProjects(3),
    });
    await setupAuth(page);
  });

  test('navigates to workspace', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // Navigate away first
    await workspace.kanbanLink.click();
    await expect(page).toHaveURL(new RegExp(`/repository/${MOCK_PROJECT_ID}/kanban`));

    // Then navigate back
    await workspace.workspaceLink.click();
    await expect(page).toHaveURL(new RegExp(`/repository/${MOCK_PROJECT_ID}/workspace`));
  });

  test('navigates to kanban', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.kanbanLink.click();
    await expect(page).toHaveURL(new RegExp(`/repository/${MOCK_PROJECT_ID}/kanban`));
  });

  test('navigates to prompt assembly', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.promptAssemblyLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/repository/${MOCK_PROJECT_ID}/prompt_assembly`)
    );
  });

  test('navigates to project architecture', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.architectureLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/repository/${MOCK_PROJECT_ID}/artifacts`)
    );
  });

  test('navigates to project settings', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.settingsLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/repository/${MOCK_PROJECT_ID}/settings`)
    );
  });

  test('AICT logo links to repositories', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.aictLogo.click();
    await expect(page).toHaveURL(/\/repositories$/);
  });

  test('user settings link navigates to /settings', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    await workspace.userSettingsLink.click();
    await expect(page).toHaveURL(/\/settings$/);
  });

  test('switching project via selector navigates to new workspace', async ({ page }) => {
    const workspace = new WorkspacePage(page);
    await workspace.goto(MOCK_PROJECT_ID);
    await workspace.waitForLoad();

    // Select a different project from the dropdown
    await workspace.projectSelector.selectOption(MOCK_PROJECT_ID_2);
    await expect(page).toHaveURL(
      new RegExp(`/repository/${MOCK_PROJECT_ID_2}/workspace`)
    );
  });
});
