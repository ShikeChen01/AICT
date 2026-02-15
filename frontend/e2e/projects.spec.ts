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

  test('shows project cards if projects exist', async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();
    
    // Wait for page to load
    await projectsPage.waitForLoad();
    
    // Either we have projects or we see an empty state
    const projectCount = await projectsPage.getProjectCount();
    
    if (projectCount > 0) {
      await expect(projectsPage.projectCards.first()).toBeVisible();
    } else {
      // Check for empty state message
      await expect(
        page.getByText(/no projects|create your first|get started/i)
      ).toBeVisible();
    }
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
