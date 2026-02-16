import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';

test.describe('Authentication', () => {
  test.describe.configure({ mode: 'serial' });

  test('shows Google-only controls on login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('button', { name: /continue with google/i })).toBeVisible();
    await expect(page.getByPlaceholder(/email/i)).toHaveCount(0);
    await expect(page.getByPlaceholder(/password/i)).toHaveCount(0);
  });

  test('seeded authenticated state lands on repositories', async ({ page }) => {
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
    await expect(page).toHaveURL(/\/repositories$/);
  });

  test('refresh on authenticated route does not get stuck loading', async ({ page }) => {
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
    await expect(page.getByText('Loading...')).toHaveCount(0);
    await expect(page).toHaveURL(/\/repositories$/);
  });

  test('failed /auth/me does not deadlock loading', async ({ page }) => {
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

  test('seeded token is sent as Authorization header for /auth/me', async ({ page }) => {
    let observedAuthHeader: string | undefined;
    await page.route('**/api/v1/auth/me', async (route) => {
      observedAuthHeader = route.request().headers()['authorization'];
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Invalid token' }),
      });
    });

    await setupAuth(page);
    await page.goto('/repositories');
    await expect.poll(() => observedAuthHeader).toBeTruthy();
    expect(observedAuthHeader).toMatch(/^Bearer /);
  });
});
