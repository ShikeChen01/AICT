/**
 * Page Object Model for the Register page.
 */

import { Page, Locator } from '@playwright/test';

export class RegisterPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly googleButton: Locator;
  readonly loginLink: Locator;
  readonly descriptionText: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /get started/i });
    this.googleButton = page.getByRole('button', { name: /continue with google/i });
    this.loginLink = page.getByRole('link', { name: /login/i });
    this.descriptionText = page.getByText(/google sign-in/i);
    this.errorMessage = page.locator('.bg-red-50 .text-red-600');
  }

  async goto(): Promise<void> {
    await this.page.goto('/register');
  }
}
