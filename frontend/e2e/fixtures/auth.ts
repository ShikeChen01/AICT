/**
 * Authentication fixtures and helpers for E2E tests.
 */

import { Page } from '@playwright/test';

const API_TOKEN = process.env.API_TOKEN || 'change-me-in-production';

/**
 * Set up authentication for the page.
 * Stores a seeded API token in localStorage for deterministic test auth.
 */
export async function setupAuth(page: Page): Promise<void> {
  await setupAuthenticatedSession(page, API_TOKEN);
}

export async function setupAuthenticatedSession(page: Page, token: string): Promise<void> {
  // Navigate first to set storage on app origin
  await page.goto('/');
  await page.evaluate((nextToken) => {
    localStorage.setItem('auth_token', nextToken);
  }, token);

  // Reload so auth bootstrap reads seeded values at startup.
  await page.reload();
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
  await setupSignedOutSession(page);
}

export async function setupSignedOutSession(page: Page): Promise<void> {
  await page.goto('/');
  await page.evaluate(async () => {
    localStorage.removeItem('auth_token');
    sessionStorage.clear();
    if ('databases' in indexedDB) {
      const databases = await indexedDB.databases();
      await Promise.all(
        databases
          .filter((db) => db.name)
          .map((db) => new Promise<void>((resolve) => {
            const request = indexedDB.deleteDatabase(db.name!);
            request.onsuccess = () => resolve();
            request.onerror = () => resolve();
            request.onblocked = () => resolve();
          }))
      );
    }
  });
  await page.reload();
}
