/**
 * Page Object Model for the Workspace page.
 * Updated: uses top-nav layout, routes are /project/{id}/workspace.
 */

import { Page, Locator, expect } from '@playwright/test';

export class WorkspacePage {
  readonly page: Page;

  // Top nav (replaces old sidebar)
  readonly topNav: Locator;
  readonly aictLogo: Locator;
  readonly projectSelector: Locator;
  readonly workspaceLink: Locator;
  readonly kanbanLink: Locator;
  readonly dashboardLink: Locator;
  readonly desktopsLink: Locator;
  readonly agentsLink: Locator;
  readonly settingsLink: Locator;
  readonly userMenu: Locator;

  // Main content area
  readonly mainContent: Locator;

  // Workspace-specific
  readonly workspaceHeading: Locator;
  readonly agentPicker: Locator;

  constructor(page: Page) {
    this.page = page;

    // Top navigation bar
    this.topNav = page.locator('[role="banner"]');
    this.aictLogo = page.locator('[aria-label*="AICT"]');
    this.projectSelector = page.locator('[data-testid="project-switcher"], button:has-text("Projects")').first();
    this.workspaceLink = page.getByRole('link', { name: /workspace/i });
    this.kanbanLink = page.getByRole('link', { name: /kanban/i });
    this.dashboardLink = page.getByRole('link', { name: /dashboard/i });
    this.desktopsLink = page.getByRole('link', { name: /desktops/i });
    this.agentsLink = page.getByRole('link', { name: /agents/i });
    this.settingsLink = page.getByRole('link', { name: /settings/i });
    this.userMenu = page.locator('[data-testid="user-menu"], button:has(img[alt])').first();

    // Main content
    this.mainContent = page.locator('.flex.min-h-0.flex-1');

    // Workspace panels
    this.workspaceHeading = page.locator('h2:has-text("Workspace")');
    this.agentPicker = page.locator('select, [data-testid="agent-picker"]').first();
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/workspace`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.topNav).toBeVisible({ timeout: 10000 });
  }
}
