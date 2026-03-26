import { Locator, Page, expect } from '@playwright/test';

export class AgentsPageObject {
  readonly page: Page;

  // Sidebar
  readonly hierarchyHeading: Locator;
  readonly agentTreeItems: Locator;

  // Tabs
  readonly promptBuilderTab: Locator;
  readonly templatesTab: Locator;
  readonly overviewTab: Locator;

  constructor(page: Page) {
    this.page = page;

    this.hierarchyHeading = page.locator('text=Agent Hierarchy');
    this.agentTreeItems = page.locator('[role="button"]').filter({ hasText: /Manager|CTO|Engineer/ });

    this.promptBuilderTab = page.locator('button:has-text("Prompt Builder")');
    this.templatesTab = page.locator('button:has-text("Templates")');
    this.overviewTab = page.locator('button:has-text("Overview")');
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/agents`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.hierarchyHeading).toBeVisible({ timeout: 10000 });
  }

  async selectAgent(name: string): Promise<void> {
    await this.page.locator(`[role="button"]:has-text("${name}")`).click();
  }

  getAgentItem(name: string): Locator {
    return this.page.locator(`[role="button"]:has-text("${name}")`);
  }
}
