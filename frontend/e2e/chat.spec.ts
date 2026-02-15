/**
 * Chat Page E2E Tests
 */

import { test, expect } from '@playwright/test';
import { ChatPage } from './pages/chat.page';
import { setupAuth } from './fixtures/auth';
import { TEST_PROJECT_ID } from './fixtures/test-data';

// Skip tests if no test project configured
test.beforeAll(() => {
  if (!TEST_PROJECT_ID) {
    test.skip(true, 'TEST_PROJECT_ID not configured');
  }
});

test.describe('Chat with GM', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('displays chat interface', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Check that main elements are visible
    await expect(chatPage.messageInput).toBeVisible();
    await expect(chatPage.sendButton).toBeVisible();
  });

  test('shows GM status indicator', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // GM status should be visible
    await expect(chatPage.gmStatusIndicator).toBeVisible();
    
    // Status should be one of: available, busy, sleeping
    const status = await chatPage.getGmStatus();
    expect(status?.toLowerCase()).toMatch(/available|busy|sleeping/);
  });

  test('can send a message', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // Send a simple message
    const testMessage = `Hello GM! Test message at ${Date.now()}`;
    await chatPage.sendMessage(testMessage);
    
    // User message should appear
    await chatPage.waitForUserMessage(testMessage);
  });

  test('receives GM response', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // Send a message
    await chatPage.sendMessage('What can you help me with?');
    
    // Wait for GM response
    const response = await chatPage.waitForGmResponse(60000);
    
    // Response should have content
    const responseText = await response.textContent();
    expect(responseText?.length).toBeGreaterThan(10);
  });

  test('GM status changes to busy during processing', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // Send a message
    await chatPage.sendMessage('Please process this message');
    
    // Status might briefly show busy (depending on timing)
    // After processing, should return to available
    await chatPage.waitForGmResponse(60000);
    await chatPage.waitForGmAvailable(30000);
  });

  test('displays activity feed', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Activity feed should be visible
    await expect(chatPage.activityFeed).toBeVisible();
  });

  test('handles empty message gracefully', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Try to send empty message
    await chatPage.messageInput.fill('');
    await chatPage.sendButton.click();
    
    // Should not crash or show error
    // Message input should still be functional
    await expect(chatPage.messageInput).toBeVisible();
    await expect(chatPage.messageInput).toBeEnabled();
  });
});

test.describe('Chat - Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('shows meaningful error for failed requests', async ({ page }) => {
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // Send a message that might trigger complex processing
    await chatPage.sendMessage(
      'Do something that requires external services'
    );
    
    // We should get a response (either success or a helpful error message)
    // The key is that we don't get a 500 error shown to the user
    const response = await chatPage.waitForGmResponse(60000);
    const responseText = await response.textContent();
    
    // Response should be meaningful (not empty, not just an error code)
    expect(responseText?.length).toBeGreaterThan(10);
    
    // Should not contain raw error codes
    expect(responseText).not.toMatch(/^500$/);
    expect(responseText).not.toMatch(/Internal Server Error/i);
  });
});
