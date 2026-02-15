/**
 * Authentication fixtures and helpers for E2E tests.
 */

import { Page } from '@playwright/test';

const API_TOKEN = process.env.API_TOKEN || 'change-me-in-production';

/**
 * Set up authentication for the page.
 * Stores the API token in localStorage for the frontend to use.
 */
export async function setupAuth(page: Page): Promise<void> {
  // Navigate to the app first to set localStorage on the correct origin
  await page.goto('/');
  
  // Set the auth token in localStorage
  await page.evaluate((token) => {
    localStorage.setItem('auth_token', token);
  }, API_TOKEN);
}

/**
 * Get the Authorization header value for API requests.
 */
export function getAuthHeader(): string {
  return `Bearer ${API_TOKEN}`;
}

/**
 * Clear authentication.
 */
export async function clearAuth(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.removeItem('auth_token');
  });
}
