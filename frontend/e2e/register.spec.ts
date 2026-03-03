import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs } from './fixtures/api-mocks';
import { RegisterPage } from './pages/register.page';

test.describe('Register Page', () => {
  test('displays registration page heading', async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(registerPage.heading).toBeVisible();
    await expect(registerPage.heading).toHaveText('Get Started');
  });

  test('shows Google sign-in button', async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(registerPage.googleButton).toBeVisible();
    await expect(registerPage.googleButton).toContainText('Continue with Google');
  });

  test('displays AICT description text', async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(registerPage.descriptionText).toBeVisible();
  });

  test('shows link to login page', async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(registerPage.loginLink).toBeVisible();
    await expect(registerPage.loginLink).toHaveAttribute('href', '/login');
  });

  test('displays error from URL params', async ({ page }) => {
    await page.goto('/register?error=Token%20expired');
    const registerPage = new RegisterPage(page);
    await expect(registerPage.errorMessage).toBeVisible();
    await expect(registerPage.errorMessage).toContainText('Token expired');
  });

  test('authenticated user is redirected away from register', async ({ page }) => {
    await mockAuthenticatedAPIs(page);
    await setupAuth(page);
    await page.goto('/register');
    await expect(page).toHaveURL(/\/repositories$/);
  });
});
