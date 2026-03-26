/**
 * Page Object Model for the Project Settings page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class SettingsPage {
  readonly page: Page;
  readonly pageTitle: Locator;
  readonly projectName: Locator;
  readonly backButton: Locator;

  // General section
  readonly nameInput: Locator;
  readonly descriptionTextarea: Locator;

  // Git section
  readonly repoUrlInput: Locator;

  // Agent Limits
  readonly maxEngineersInput: Locator;

  // Rate Limits
  readonly callsPerHourInput: Locator;
  readonly tokensPerHourInput: Locator;

  // Budget
  readonly dailyTokenBudgetInput: Locator;
  readonly dailyCostBudgetInput: Locator;

  // Secrets
  readonly secretNameInput: Locator;
  readonly secretValueInput: Locator;
  readonly addSecretButton: Locator;
  readonly envUploadButton: Locator;
  readonly secretsTable: Locator;

  // Actions
  readonly saveButton: Locator;
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.pageTitle = page.getByRole('heading', { name: /project settings/i });
    this.projectName = page.locator('.text-sm.text-\\[var\\(--text-muted\\)\\]');
    this.backButton = page.getByRole('link', { name: /projects/i }).first();

    // Settings page labels don't use htmlFor/id — use scoped locators.
    // General section: first required text input on the page
    this.nameInput = page.locator('input[type="text"][required]').first();
    this.descriptionTextarea = page.locator('form textarea').first();

    // Git section
    this.repoUrlInput = page.locator('input[type="url"]');

    // Agent Limits: the number input with min=1 max=20
    this.maxEngineersInput = page.locator('input[type="number"][min="1"][max="20"]');

    // Rate Limits: number inputs with step=10 and step=10000
    this.callsPerHourInput = page.locator('input[type="number"][step="10"]');
    this.tokensPerHourInput = page.locator('input[type="number"][step="10000"]').first();

    // Budget: number inputs in the budget section
    this.dailyTokenBudgetInput = page.locator('input[type="number"][step="10000"]').nth(1);
    this.dailyCostBudgetInput = page.locator('input[type="number"][step="0.5"]');

    // Secrets
    this.secretNameInput = page.getByPlaceholder('e.g. GITHUB_TOKEN');
    this.secretValueInput = page.locator('input[type="password"][placeholder="••••••••"]');
    this.addSecretButton = page.getByRole('button', { name: /add \/ update/i });
    this.envUploadButton = page.getByRole('button', { name: /upload \.env file/i });
    this.secretsTable = page.locator('table').last();

    // Actions
    this.saveButton = page.getByRole('button', { name: /save changes/i });
    this.successMessage = page.locator('text=Settings saved');
    this.errorMessage = page.locator('[class*="color-danger"] .text-sm, [class*="danger"] span.text-sm');
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/settings`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.pageTitle).toBeVisible();
  }
}
