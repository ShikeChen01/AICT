import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs, mockProjectAPIs } from './fixtures/api-mocks';
import {
  MOCK_PROJECT_ID,
  mockProjectSettings,
} from './fixtures/mock-data';
import { SettingsPage } from './pages/settings.page';

test.describe('Project Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedAPIs(page);
    await mockProjectAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  test('displays settings page with header', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(settings.pageTitle).toHaveText('Project Settings');
  });

  test('displays all section headings', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(page.getByRole('heading', { name: /general/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /git integration/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /agent limits/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /rate limits/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /budget/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /project secrets/i })).toBeVisible();
  });

  test('loads existing project data into form fields', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();
    // Wait for data to populate
    await expect(settings.nameInput).toBeVisible();
    await expect(settings.nameInput).toHaveValue('Test Repository', { timeout: 15000 });
    await expect(settings.repoUrlInput).toHaveValue('https://github.com/test-org/test-repo');
  });

  test('general section shows name and description fields', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();
    await expect(settings.nameInput).toBeVisible({ timeout: 15000 });
    await expect(settings.descriptionTextarea).toBeVisible();
  });

  test('git integration section shows repo URL field', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();
    await expect(settings.repoUrlInput).toBeVisible({ timeout: 15000 });
    await expect(settings.repoUrlInput).toHaveAttribute('type', 'url');
  });

  test('agent limits shows max engineers input', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();
    await expect(settings.maxEngineersInput).toBeVisible({ timeout: 15000 });
    await expect(settings.maxEngineersInput).toHaveAttribute('type', 'number');
    await expect(settings.maxEngineersInput).toHaveAttribute('min', '1');
    await expect(settings.maxEngineersInput).toHaveAttribute('max', '20');
    await expect(settings.maxEngineersInput).toHaveValue('5');
  });

  test('rate limits section shows calls/hour and tokens/hour inputs', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(settings.callsPerHourInput).toBeVisible({ timeout: 15000 });
    await expect(settings.tokensPerHourInput).toBeVisible();
  });

  test('budget section shows daily token and cost budget inputs', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(settings.dailyTokenBudgetInput).toBeVisible({ timeout: 15000 });
    await expect(settings.dailyCostBudgetInput).toBeVisible();
  });

  test('displays usage statistics when available', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(page.getByText(/today's usage/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/input tokens/i).first()).toBeVisible();
    await expect(page.getByText(/output tokens/i).first()).toBeVisible();
    await expect(page.getByText(/est\. cost/i).first()).toBeVisible();
  });

  test('secrets section shows existing secrets', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(page.getByText('GITHUB_TOKEN')).toBeVisible();
    await expect(page.getByText('OPENAI_API_KEY')).toBeVisible();
  });

  test('secrets section shows add form', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(settings.secretNameInput).toBeVisible();
    await expect(settings.secretValueInput).toBeVisible();
    await expect(settings.addSecretButton).toBeVisible();
  });

  test('env upload button is visible', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await expect(settings.envUploadButton).toBeVisible();
  });

  test('save button triggers API call and shows success', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    // Wait for form to fully load
    await expect(settings.nameInput).toBeVisible({ timeout: 15000 });
    await settings.nameInput.clear();
    await settings.nameInput.fill('Updated Repository Name');
    await settings.saveButton.click();

    await expect(page.locator('text=Settings saved')).toBeVisible();
  });

  test('displays error on save failure', async ({ page }) => {
    // Override both project PATCH and settings PATCH to fail
    await page.route(`**/api/v1/repositories/${MOCK_PROJECT_ID}`, async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        });
      } else {
        await route.fallback();
      }
    });
    await page.route(`**/api/v1/repositories/${MOCK_PROJECT_ID}/settings`, async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        });
      } else {
        await route.fallback();
      }
    });

    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    await settings.saveButton.click();
    // Error message should appear (uses danger color styling)
    await expect(page.locator('text=/error|failed/i').first()).toBeVisible({ timeout: 10000 });
  });

  test('AICT logo navigates to projects', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto(MOCK_PROJECT_ID);
    await settings.waitForLoad();

    // The settings page uses top-nav; clicking AICT logo goes to projects
    await page.locator('[aria-label*="AICT"]').click();
    await expect(page).toHaveURL(/\/projects$/);
  });

  test('shows project not found for invalid project', async ({ page }) => {
    const invalidId = 'invalid-project-id';
    await page.route(`**/api/v1/repositories/${invalidId}`, async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Not found' }),
      });
    });
    await page.route(`**/api/v1/repositories/${invalidId}/settings`, async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Not found' }),
      });
    });
    await page.route(`**/api/v1/repositories/${invalidId}/usage`, async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Not found' }),
      });
    });
    await page.route(new RegExp(`/api/v1/repositories/${invalidId}/secrets`), async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Not found' }),
      });
    });

    await page.goto(`/project/${invalidId}/settings`);
    await expect(page.getByText(/project not found/i)).toBeVisible();
  });
});
