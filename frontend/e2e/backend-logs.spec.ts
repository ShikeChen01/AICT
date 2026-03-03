import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID } from './fixtures/mock-data';

test.describe('Backend Logs / AI Usage Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('displays AI usage page heading with project name', async ({ page }) => {
    await page.goto(`/repository/${MOCK_PROJECT_ID}/backend-logs`);
    // The h1 heading contains "AI Usage — <project name>"
    const heading = page.locator('h1').filter({ hasText: /ai usage/i });
    await expect(heading).toBeVisible({ timeout: 15000 });
    await expect(heading).toContainText('Test Repository');
  });

  test('shows description text', async ({ page }) => {
    await page.goto(`/repository/${MOCK_PROJECT_ID}/backend-logs`);
    await expect(page.getByText(/real-time llm call stream/i)).toBeVisible();
  });

  test('shows back to workspace link', async ({ page }) => {
    await page.goto(`/repository/${MOCK_PROJECT_ID}/backend-logs`);
    const backLink = page.getByRole('link', { name: /back to workspace/i });
    await expect(backLink).toBeVisible();
    await expect(backLink).toHaveAttribute(
      'href',
      `/repository/${MOCK_PROJECT_ID}/workspace`
    );
  });

  test('renders main content area', async ({ page }) => {
    await page.goto(`/repository/${MOCK_PROJECT_ID}/backend-logs`);
    await expect(page.locator('main')).toBeVisible();
  });
});
