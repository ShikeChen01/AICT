import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockAuthenticatedAPIs } from './fixtures/api-mocks';
import { LoginPage } from './pages/login.page';

test.describe('Login Page', () => {
  test('displays login page heading', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(loginPage.heading).toBeVisible();
    await expect(loginPage.heading).toHaveText('Login');
  });

  test('shows Google sign-in button', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(loginPage.googleButton).toBeVisible();
    await expect(loginPage.googleButton).toContainText('Continue with Google');
  });

  test('shows sign-in description', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(page.getByText(/sign in with your google account/i)).toBeVisible();
  });

  test('shows link to registration', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(loginPage.registerLink).toBeVisible();
    await expect(loginPage.registerLink).toHaveAttribute('href', '/register');
  });

  test('displays error from URL params', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.gotoWithError('Something went wrong');
    await expect(loginPage.errorMessage).toBeVisible();
    await expect(loginPage.errorMessage).toContainText('Something went wrong');
  });

  test('authenticated user is redirected to repositories', async ({ page }) => {
    await mockAuthenticatedAPIs(page);
    await setupAuth(page);
    await page.goto('/login');
    await expect(page).toHaveURL(/\/repositories$/);
  });
});
