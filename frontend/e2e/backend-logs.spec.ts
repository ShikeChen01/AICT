import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID } from './fixtures/mock-data';

test.describe('Logs / AI Usage Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('displays logs page heading with project name', async ({ page }) => {
    await page.goto(`/project/${MOCK_PROJECT_ID}/logs`);
    const heading = page.locator('h1').filter({ hasText: /logs/i });
    await expect(heading).toBeVisible({ timeout: 15000 });
    await expect(heading).toContainText('Test Repository');
  });

  test('shows description text', async ({ page }) => {
    await page.goto(`/project/${MOCK_PROJECT_ID}/logs`);
    await expect(page.getByText(/real-time llm call stream/i)).toBeVisible();
  });

  test('renders main content area', async ({ page }) => {
    await page.goto(`/project/${MOCK_PROJECT_ID}/logs`);
    await expect(page.locator('main')).toBeVisible();
  });
});
