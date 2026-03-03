/**
 * Page Object Model for the Workspace page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class WorkspacePage {
  readonly page: Page;
  // Sidebar
  readonly sidebar: Locator;
  readonly projectSelector: Locator;
  readonly aictLogo: Locator;
  readonly workspaceLink: Locator;
  readonly kanbanLink: Locator;
  readonly promptAssemblyLink: Locator;
  readonly architectureLink: Locator;
  readonly settingsLink: Locator;
  readonly aiUsageLink: Locator;
  readonly userSettingsLink: Locator;
  // Main content
  readonly mainContent: Locator;
  // Monitoring panel
  readonly liveStreamPanel: Locator;
  readonly agentsPanel: Locator;
  readonly activityTimeline: Locator;

  constructor(page: Page) {
    this.page = page;
    // Sidebar
    this.sidebar = page.locator('aside').first();
    this.projectSelector = page.locator('#project-selector');
    this.aictLogo = page.getByRole('heading', { name: /aict/i });
    this.workspaceLink = page.getByRole('link', { name: /workspace/i });
    this.kanbanLink = page.getByRole('link', { name: /kanban/i });
    this.promptAssemblyLink = page.getByRole('link', { name: /prompt assembly/i });
    this.architectureLink = page.getByRole('link', { name: /project architecture/i });
    this.settingsLink = page.getByRole('link', { name: /project settings/i });
    this.aiUsageLink = page.getByRole('link', { name: /ai usage/i });
    this.userSettingsLink = page.getByRole('link', { name: /user settings/i });
    // Main
    this.mainContent = page.locator('main');
    // Panels — use heading role to avoid matching placeholder text
    this.liveStreamPanel = page.getByRole('heading', { name: 'Live stream' });
    this.agentsPanel = page.getByRole('heading', { name: 'Agents' });
    this.activityTimeline = page.getByRole('heading', { name: 'Activity timeline' });
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/repository/${projectId}/workspace`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.sidebar).toBeVisible();
    await expect(this.mainContent).toBeVisible();
  }
}
