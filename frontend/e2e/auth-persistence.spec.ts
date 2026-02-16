import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';

test.describe('Authentication Persistence', () => {
  test('multiple refresh cycles preserve session without loading deadlock', async ({ page }) => {
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

    await setupAuth(page);
    await page.goto('/repositories');
    await page.reload();
    await page.reload();

    await expect(page.getByText('Loading...')).toHaveCount(0);
    await expect(page).toHaveURL(/\/repositories$/);
  });

  test('invalid /auth/me response recovers without loading deadlock', async ({ page }) => {
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Invalid token' }),
      });
    });

    await setupAuth(page);
    await page.goto('/repositories');

    await expect(page.getByText('Loading...')).toHaveCount(0);
  });
});
