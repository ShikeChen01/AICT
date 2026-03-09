/**
 * Page Object Model for the Projects page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class ProjectsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly newProjectButton: Locator;
  readonly projectCards: Locator;
  readonly projectNameInput: Locator;
  readonly projectRepoInput: Locator;
  readonly createButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /^projects$/i });
    this.newProjectButton = page.getByRole('button', { name: /new project|create project/i });
    this.projectCards = page.getByTestId('project-card');
    this.projectNameInput = page.getByLabel(/name/i);
    this.projectRepoInput = page.getByLabel(/repository|repo/i);
    this.createButton = page.getByRole('button', { name: /create/i });
  }

  /**
   * Navigate to the projects page.
   */
  async goto(): Promise<void> {
    await this.page.goto('/projects');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for the projects page to load.
   */
  async waitForLoad(): Promise<void> {
    await expect(this.heading).toBeVisible();
  }

  /**
   * Get the number of project cards.
   */
  async getProjectCount(): Promise<number> {
    return this.projectCards.count();
  }

  /**
   * Click on a project card by name.
   */
  async selectProject(name: string): Promise<void> {
    await this.projectCards.filter({ hasText: name }).click();
  }

  /**
   * Open the new project dialog.
   */
  async openNewProjectDialog(): Promise<void> {
    await this.newProjectButton.click();
  }

  /**
   * Create a new project.
   */
  async createProject(name: string, repoUrl: string): Promise<void> {
    await this.openNewProjectDialog();
    await this.projectNameInput.fill(name);
    await this.projectRepoInput.fill(repoUrl);
    await this.createButton.click();
    
    // Wait for the project to appear
    await expect(this.projectCards.filter({ hasText: name })).toBeVisible();
  }

  /**
   * Check if a project exists.
   */
  async hasProject(name: string): Promise<boolean> {
    const card = this.projectCards.filter({ hasText: name });
    return await card.count() > 0;
  }
}
