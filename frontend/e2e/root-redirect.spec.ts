import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs } from './fixtures/api-mocks';
import { mockProjects, MOCK_PROJECT_ID } from './fixtures/mock-data';

test.describe('Root URL Redirect Logic', () => {
  test('root URL with projects redirects to first project dashboard', async ({ page }) => {
    const projects = mockProjects(2);
    await mockAuthenticatedAPIs(page, { projects });
    await setupAuth(page);

    await page.goto('/');
    await expect(page).toHaveURL(new RegExp(`/project/${MOCK_PROJECT_ID}/dashboard`));
  });

  test('root URL with no projects redirects to /projects', async ({ page }) => {
    await mockAuthenticatedAPIs(page, { projects: [] });
    await setupAuth(page);

    await page.goto('/');
    await expect(page).toHaveURL(/\/projects$/);
  });

  test('unknown route redirects to root then resolves', async ({ page }) => {
    await mockAuthenticatedAPIs(page, { projects: [] });
    await setupAuth(page);

    await page.goto('/nonexistent-page');
    // Should eventually end up at /projects since there are no projects
    await expect(page).toHaveURL(/\/projects$/);
  });

  test('unauthenticated root URL redirects to login', async ({ page }) => {
    // No auth setup — should redirect to /login
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });
});
