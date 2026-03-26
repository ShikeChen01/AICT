import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs } from './fixtures/api-mocks';
import { mockUser } from './fixtures/mock-data';
import { UserSettingsPage } from './pages/user-settings.page';

test.describe('User Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedAPIs(page);
    await setupAuth(page);
  });

  test('displays user settings page heading', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();
    await expect(settingsPage.heading).toHaveText('User Settings');
  });

  test('shows user email', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();
    await expect(page.getByText('e2e-user@example.com')).toBeVisible();
  });

  test('shows display name input', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();
    await expect(settingsPage.displayNameInput).toBeVisible();
  });

  test('shows GitHub PAT input field', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();
    await expect(settingsPage.githubTokenInput).toBeVisible();
    await expect(settingsPage.githubTokenInput).toHaveAttribute('type', 'password');
  });

  test('shows placeholder when GitHub token is configured', async ({ page }) => {
    // Override with a user that has github_token_set: true
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockUser({ github_token_set: true })),
      });
    });

    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();
    await expect(settingsPage.githubTokenInput).toHaveAttribute(
      'placeholder',
      /configured/i
    );
  });

  test('can update display name', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();

    await settingsPage.displayNameInput.clear();
    await settingsPage.displayNameInput.fill('New Name');
    await settingsPage.save();

    await expect(settingsPage.successMessage).toBeVisible();
    await expect(settingsPage.successMessage).toContainText('Settings saved');
  });

  test('can update GitHub token', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();

    await settingsPage.githubTokenInput.fill('ghp_test_token_123');
    await settingsPage.save();

    await expect(settingsPage.successMessage).toBeVisible();
    await expect(settingsPage.successMessage).toContainText('Settings saved');
  });

  test('displays error on save failure', async ({ page }) => {
    // Override PATCH to fail
    await page.route('**/api/v1/auth/me', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ message: 'Internal server error' }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockUser()),
        });
      }
    });

    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();

    await settingsPage.displayNameInput.fill('Fail Name');
    await settingsPage.save();

    await expect(settingsPage.errorMessage).toBeVisible();
  });

  test('back button navigates to projects', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();

    await settingsPage.backButton.click();
    await expect(page).toHaveURL(/\/projects$/);
  });

  test('shows save, back, and logout buttons', async ({ page }) => {
    const settingsPage = new UserSettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForLoad();

    await expect(settingsPage.saveButton).toBeVisible();
    await expect(settingsPage.backButton).toBeVisible();
    await expect(settingsPage.logoutButton).toBeVisible();
  });
});
