import { Locator, Page, expect } from '@playwright/test';

export class DashboardPage {
  readonly page: Page;

  // Header
  readonly projectName: Locator;
  readonly emergencyStopButton: Locator;

  // Stat cards
  readonly costToday: Locator;
  readonly tokensToday: Locator;
  readonly callsPerHour: Locator;

  // Sections
  readonly agentFleetHeading: Locator;
  readonly sandboxHeading: Locator;
  readonly activityHeading: Locator;

  // Agent fleet
  readonly agentCards: Locator;

  // Sandbox thumbnails
  readonly openSandboxButton: Locator;

  // Navigation
  readonly manageAgentsLink: Locator;

  constructor(page: Page) {
    this.page = page;

    this.projectName = page.locator('h1');
    this.emergencyStopButton = page.locator('button:has-text("Emergency Stop All")');

    this.costToday = page.locator('text=/\\$[0-9]/');
    this.tokensToday = page.locator('text=/tokens/i');
    this.callsPerHour = page.locator('text=/calls/i');

    this.agentFleetHeading = page.locator('#fleet-heading');
    this.sandboxHeading = page.locator('#sandbox-heading');
    this.activityHeading = page.locator('#activity-heading');

    this.agentCards = page.locator('[aria-labelledby="fleet-heading"] [role="button"], [aria-labelledby="fleet-heading"] button');

    this.openSandboxButton = page.locator('text=Open Sandbox');

    this.manageAgentsLink = page.locator('text=Manage');
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/dashboard`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.projectName).toBeVisible({ timeout: 10000 });
  }
}
