import { expect, test } from '@playwright/test';

import { setupAuthenticatedSession } from './fixtures/auth';

test.describe('Authentication Redirects', () => {
  test('unauthenticated access to protected route redirects to /login', async ({ page }) => {
    await page.goto('/repositories');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('authenticated session can access protected route', async ({ page }) => {
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'e2e-user@example.com',
          display_name: 'E2E User',
          github_token_set: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });
    await page.route('**/api/v1/repositories', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await setupAuthenticatedSession(page, process.env.API_TOKEN || 'change-me-in-production');
    await page.goto('/repositories');
    await expect(page).toHaveURL(/\/repositories$/);
  });

  test('authenticated user visiting /login redirects to /repositories', async ({ page }) => {
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'e2e-user@example.com',
          display_name: 'E2E User',
          github_token_set: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });
    await page.route('**/api/v1/repositories', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await setupAuthenticatedSession(page, process.env.API_TOKEN || 'change-me-in-production');
    await page.goto('/login');
    await expect(page).toHaveURL(/\/repositories$/);
  });
});
