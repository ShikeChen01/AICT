/**
 * Page Object Model for the User Settings page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class UserSettingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emailText: Locator;
  readonly displayNameInput: Locator;
  readonly githubTokenInput: Locator;
  readonly saveButton: Locator;
  readonly backButton: Locator;
  readonly logoutButton: Locator;
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /user settings/i });
    this.emailText = page.locator('.text-gray-600').first();
    // Labels in UserSettings don't use htmlFor/id, so locate by parent div
    this.displayNameInput = page.locator('div:has(> label:text("Display name")) input').first();
    this.githubTokenInput = page.locator('div:has(> label:text-matches("GitHub Personal Access Token", "i")) input[type="password"]');
    this.saveButton = page.getByRole('button', { name: /save/i });
    this.backButton = page.getByRole('button', { name: /back/i });
    this.logoutButton = page.getByRole('button', { name: /logout/i });
    this.successMessage = page.locator('.text-green-600');
    this.errorMessage = page.locator('.text-red-600');
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings');
  }

  async waitForLoad(): Promise<void> {
    await expect(this.heading).toBeVisible();
  }

  async save(): Promise<void> {
    await this.saveButton.click();
  }
}
