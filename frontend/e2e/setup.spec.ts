/**
 * Setup verification test.
 * 
 * This test verifies that Playwright is configured correctly.
 * It doesn't require the frontend or backend to be running.
 */

import { test, expect } from '@playwright/test';

test.describe('Playwright Setup Verification', () => {
  test('playwright is configured correctly', async () => {
    // Simple assertion to verify Playwright works
    expect(true).toBe(true);
  });

  test('can make HTTP requests', async ({ request }) => {
    // Verify request context works
    const response = await request.get('https://httpbin.org/get');
    expect(response.ok()).toBe(true);
  });

  test('environment variables are accessible', async () => {
    // Verify we can access env vars
    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
    expect(frontendUrl).toBeTruthy();
  });
});
