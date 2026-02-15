/**
 * GitHub Integration E2E Tests
 * 
 * These tests validate the full agent workflow by:
 * 1. Sending a chat message to the Manager asking to create a repo
 * 2. Waiting for the Engineer to complete the work
 * 3. Verifying the repo exists on GitHub
 * 4. Cleaning up the test repo using GITHUB_TOKEN_TEST
 * 
 * IMPORTANT:
 * - The application uses GITHUB_TOKEN for all operations
 * - Test cleanup uses GITHUB_TOKEN_TEST (separate token for cleanup only)
 */

import { test, expect } from '@playwright/test';
import { ChatPage } from './pages/chat.page';
import { setupAuth } from './fixtures/auth';
import {
  TEST_PROJECT_ID,
  GITHUB_TEST_OWNER,
  generateTestRepoName,
  requireGitHubTestConfig,
} from './fixtures/test-data';
import { deleteTestRepo, trackRepoForCleanup } from './utils/github-cleanup';

// Skip all tests if GitHub integration is not configured
test.beforeAll(() => {
  try {
    requireGitHubTestConfig();
  } catch (error) {
    test.skip(true, (error as Error).message);
  }
});

test.describe('GitHub Integration - Full Agent Workflow', () => {
  // Generate unique repo name for this test run
  const repoName = generateTestRepoName();
  
  test.afterAll(async () => {
    // Cleanup: Delete the test repo using GITHUB_TOKEN_TEST
    console.log(`[Test Cleanup] Deleting test repo: ${GITHUB_TEST_OWNER}/${repoName}`);
    try {
      await deleteTestRepo(GITHUB_TEST_OWNER, repoName);
    } catch (error) {
      console.error('[Test Cleanup] Failed to delete repo:', error);
    }
  });

  test('Manager creates repo and pushes readme via Engineer', async ({ page, request }) => {
    // Track repo for cleanup in case of test failure
    trackRepoForCleanup(GITHUB_TEST_OWNER, repoName);
    
    // 1. Set up authentication
    await setupAuth(page);
    
    // 2. Navigate to chat
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // 3. Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // 4. Send instruction to Manager
    const instruction = `Create a new GitHub repository named "${repoName}" under the user "${GITHUB_TEST_OWNER}" and push a README.md file with the content "# Test Repository\n\nThis repo was created by E2E test at ${new Date().toISOString()}"`;
    
    await chatPage.sendMessage(instruction);
    
    // 5. Wait for user message to appear
    await chatPage.waitForUserMessage(repoName);
    
    // 6. Wait for Manager acknowledgment (should mention dispatching or engineer)
    await chatPage.waitForGmResponseContaining(/dispatch|engineer|task|working|queue/i, 60000);
    
    // 7. Wait for Engineer job completion (via activity feed or WebSocket)
    // This can take a while as the engineer needs to actually create the repo
    await chatPage.waitForActivityContent(/completed|success|created|pushed/i, 180000);
    
    // 8. Verify repo exists on GitHub using the GITHUB_TOKEN (same token app uses)
    // Note: We use the page's request context which doesn't have auth,
    // so we pass the token explicitly
    const githubToken = process.env.GITHUB_TOKEN;
    expect(githubToken, 'GITHUB_TOKEN is required to verify repo creation').toBeTruthy();
    
    const repoResponse = await request.get(
      `https://api.github.com/repos/${GITHUB_TEST_OWNER}/${repoName}`,
      {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'AICT-E2E-Tests',
        },
      }
    );
    
    expect(repoResponse.status(), 'Repository should exist').toBe(200);
    
    // 9. Verify README exists
    const readmeResponse = await request.get(
      `https://api.github.com/repos/${GITHUB_TEST_OWNER}/${repoName}/contents/README.md`,
      {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'AICT-E2E-Tests',
        },
      }
    );
    
    expect(readmeResponse.status(), 'README.md should exist').toBe(200);
    
    // 10. Verify README content (base64 decoded)
    const readmeData = await readmeResponse.json();
    const readmeContent = Buffer.from(readmeData.content, 'base64').toString('utf-8');
    expect(readmeContent).toContain('Test Repository');
  });

  test('Manager provides feedback on failed repo creation', async ({ page }) => {
    // This test verifies error handling when repo creation fails
    // (e.g., due to invalid name or permissions)
    
    // 1. Set up authentication
    await setupAuth(page);
    
    // 2. Navigate to chat
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    
    // 3. Wait for GM to be available
    await chatPage.waitForGmAvailable();
    
    // 4. Send an invalid instruction (repo name with invalid characters)
    const invalidRepoName = 'test--invalid..name!!';
    await chatPage.sendMessage(
      `Create a GitHub repository named "${invalidRepoName}"`
    );
    
    // 5. Wait for Manager response - should indicate an error or explain the issue
    // The Manager should gracefully handle the error and inform the user
    await chatPage.waitForGmResponseContaining(
      /error|invalid|failed|cannot|unable|issue|problem/i,
      60000
    );
    
    // The important thing is that we get a meaningful response, not a 500 error
    const messages = await chatPage.getMessages();
    const gmMessages = messages.filter(m => m.role === 'gm');
    expect(gmMessages.length, 'Should have at least one GM response').toBeGreaterThan(0);
  });
});

test.describe('GitHub Integration - Job Status Tracking', () => {
  test('can track engineer job progress via WebSocket', async ({ page }) => {
    // Skip if not configured
    try {
      requireGitHubTestConfig();
    } catch (error) {
      test.skip(true, (error as Error).message);
      return;
    }
    
    // This test verifies that job status events are properly broadcast
    const repoName = generateTestRepoName();
    trackRepoForCleanup(GITHUB_TEST_OWNER, repoName);
    
    // Set up auth and navigate
    await setupAuth(page);
    const chatPage = new ChatPage(page);
    await chatPage.goto(TEST_PROJECT_ID);
    await chatPage.waitForGmAvailable();
    
    // Listen for WebSocket events
    const jobEvents: string[] = [];
    
    await page.evaluate(() => {
      // Hook into WebSocket to capture events
      const originalWs = window.WebSocket;
      window.WebSocket = class extends originalWs {
        constructor(url: string | URL, protocols?: string | string[]) {
          super(url, protocols);
          this.addEventListener('message', (event) => {
            try {
              const data = JSON.parse(event.data);
              if (data.type?.startsWith('job_')) {
                (window as unknown as { __jobEvents: string[] }).__jobEvents = 
                  (window as unknown as { __jobEvents: string[] }).__jobEvents || [];
                (window as unknown as { __jobEvents: string[] }).__jobEvents.push(data.type);
              }
            } catch {
              // Ignore non-JSON messages
            }
          });
        }
      };
      (window as unknown as { __jobEvents: string[] }).__jobEvents = [];
    });
    
    // Send instruction
    await chatPage.sendMessage(
      `Create a GitHub repository named "${repoName}" with a README.md file`
    );
    
    // Wait for completion
    await chatPage.waitForActivityContent(/completed|success/i, 180000);
    
    // Check captured events
    const capturedEvents = await page.evaluate(() => {
      return (window as unknown as { __jobEvents: string[] }).__jobEvents || [];
    });
    
    // We should have received job status events
    expect(capturedEvents.length, 'Should have received job events').toBeGreaterThan(0);
    
    // Clean up
    await deleteTestRepo(GITHUB_TEST_OWNER, repoName);
  });
});
