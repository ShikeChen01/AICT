/**
 * Projects Page E2E Tests
 */

import { test, expect } from '@playwright/test';
import { ProjectsPage } from './pages/projects.page';
import { setupAuth } from './fixtures/auth';

test.describe('Projects Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('displays projects page heading', async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();
    
    await expect(projectsPage.heading).toBeVisible();
  });

  test('shows project cards or empty state', async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();
    await projectsPage.waitForLoad();

    // Wait for the API call to finish: either project cards appear or the empty state shows
    const projectCard = projectsPage.projectCards.first();
    const emptyState = page.getByRole('heading', { name: /no projects yet/i });

    await expect(projectCard.or(emptyState)).toBeVisible({ timeout: 15_000 });
  });

  test('can navigate to project chat', async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();
    await projectsPage.waitForLoad();
    
    const projectCount = await projectsPage.getProjectCount();
    
    if (projectCount > 0) {
      // Click first project
      await projectsPage.projectCards.first().click();
      
      // Should navigate to project page (chat or dashboard)
      await expect(page).toHaveURL(/\/project\/[a-f0-9-]+/);
    }
  });

  test('new project button is visible', async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();
    await projectsPage.waitForLoad();
    
    await expect(projectsPage.newProjectButton).toBeVisible();
  });
});
