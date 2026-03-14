import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs } from './fixtures/api-mocks';
import { mockProject, mockProjects, MOCK_PROJECT_ID } from './fixtures/mock-data';

test.describe('Repositories Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedAPIs(page);
    await setupAuth(page);
  });

  test('displays projects heading and subtext', async ({ page }) => {
    await page.goto('/repositories');
    await expect(page.getByRole('heading', { name: /^projects$/i })).toBeVisible();
    await expect(page.getByText(/design, deploy, and manage/i)).toBeVisible();
  });

  test('shows empty state when no projects', async ({ page }) => {
    await page.route('**/api/v1/repositories', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }
    });

    await page.goto('/repositories');
    await expect(page.getByText(/no projects yet/i)).toBeVisible();
  });

  test('empty state shows create and import buttons', async ({ page }) => {
    await page.route('**/api/v1/repositories', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }
    });

    await page.goto('/repositories');
    await expect(page.getByText(/no projects yet/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /new project/i })).toHaveCount(2);
    await expect(page.getByRole('button', { name: /import project/i })).toHaveCount(2);
  });

  test('displays project cards in grid', async ({ page }) => {
    const projects = mockProjects(3);
    await page.route('**/api/v1/repositories', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(projects),
        });
      }
    });

    await page.goto('/repositories');
    for (const proj of projects) {
      await expect(page.getByText(proj.name)).toBeVisible();
    }
  });

  test('project card shows name and description', async ({ page }) => {
    const project = mockProject({
      name: 'My Repo',
      description: 'Repository description text',
    });
    await page.route('**/api/v1/repositories', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([project]),
        });
      }
    });

    await page.goto('/repositories');
    await expect(page.getByText('My Repo')).toBeVisible();
    await expect(page.getByText('Repository description text')).toBeVisible();
  });

  test('can open project workspace from card', async ({ page }) => {
    const project = mockProject();
    await page.route('**/api/v1/repositories', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([project]),
        });
      }
    });

    await page.goto('/repositories');
    await page.getByText(/open project/i).click();
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/workspace`));
  });

  test('new project button opens create modal', async ({ page }) => {
    await page.goto('/repositories');
    // The button in the header (/repositories redirects to /projects)
    await page.getByRole('button', { name: /new project/i }).first().click();
    await expect(page.getByRole('heading', { name: /create new project/i })).toBeVisible();
  });

  test('import project button opens import modal', async ({ page }) => {
    await page.goto('/repositories');
    await page.getByRole('button', { name: /import project/i }).first().click();
    await expect(page.getByRole('heading', { name: /import project/i })).toBeVisible();
  });

  test('create modal has name, description, and optional repository URL', async ({ page }) => {
    await page.goto('/repositories');
    await page.getByRole('button', { name: /new project/i }).first().click();

    // Labels don't use htmlFor, so locate by text within the modal
    const modal = page.locator('.relative.mx-4');
    await expect(modal.getByText(/project name/i)).toBeVisible();
    await expect(modal.getByPlaceholder('my-project')).toBeVisible();
    await expect(modal.getByText(/description/i).first()).toBeVisible();
    await expect(modal.getByText(/repository url/i)).toBeVisible();
    await expect(modal.getByPlaceholder('https://github.com/user/repo')).toBeVisible();
  });

  test('import modal has name, description, and URL fields', async ({ page }) => {
    await page.goto('/repositories');
    await page.getByRole('button', { name: /import project/i }).first().click();

    const modal = page.locator('.relative.mx-4');
    await expect(modal.getByText(/project name/i)).toBeVisible();
    await expect(modal.getByPlaceholder('my-project')).toBeVisible();
    await expect(modal.getByText(/description/i).first()).toBeVisible();
    await expect(modal.getByText(/project url/i)).toBeVisible();
    await expect(modal.getByPlaceholder('https://github.com/user/repo')).toBeVisible();
  });

  test('cancel button closes modal', async ({ page }) => {
    await page.goto('/repositories');
    await page.getByRole('button', { name: /new project/i }).first().click();
    await expect(page.getByRole('heading', { name: /create new project/i })).toBeVisible();

    await page.getByRole('button', { name: /cancel/i }).click();
    await expect(page.getByRole('heading', { name: /create new project/i })).toHaveCount(0);
  });

  test('user settings button navigates to /settings', async ({ page }) => {
    await page.goto('/repositories');
    await page.getByRole('link').filter({ hasText: /user settings/i }).click();
    await expect(page).toHaveURL(/\/settings$/);
  });

  test('shows loading spinner while fetching projects', async ({ page }) => {
    // Slow down the API to observe loading state
    await page.route('**/api/v1/repositories', async (route) => {
      await new Promise((r) => setTimeout(r, 2000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/repositories');
    // Should show a loading spinner while waiting
    await expect(page.locator('.animate-spin')).toBeVisible({ timeout: 5000 });
  });
});
