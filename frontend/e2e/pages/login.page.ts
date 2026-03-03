/**
 * Page Object Model for the Login page.
 */

import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly googleButton: Locator;
  readonly registerLink: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /login/i });
    this.googleButton = page.getByRole('button', { name: /continue with google/i });
    this.registerLink = page.getByRole('link', { name: /get started/i });
    this.errorMessage = page.locator('.bg-red-50 .text-red-600');
  }

  async goto(): Promise<void> {
    await this.page.goto('/login');
  }

  async gotoWithError(errorText: string): Promise<void> {
    await this.page.goto(`/login?error=${encodeURIComponent(errorText)}`);
  }
}
