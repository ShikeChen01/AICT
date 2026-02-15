/**
 * Playwright global teardown.
 * Runs after all tests complete to clean up resources.
 */

import * as dotenv from 'dotenv';

// Load test environment
dotenv.config({ path: '.env.test' });
dotenv.config({ path: '.env.test.local' });

const GITHUB_TEST_OWNER = process.env.GITHUB_TEST_OWNER;
const CLEANUP_TEST_REPOS = process.env.CLEANUP_TEST_REPOS === 'true';

async function globalTeardown(): Promise<void> {
  console.log('\n[Global Teardown] Starting cleanup...');
  
  // Clean up GitHub test repos if configured
  if (CLEANUP_TEST_REPOS && GITHUB_TEST_OWNER && process.env.GITHUB_TOKEN_TEST) {
    try {
      // Dynamic import to avoid issues if octokit isn't installed
      const { cleanupTestRepos, cleanupTrackedRepos } = await import('./utils/github-cleanup');
      
      // First clean up any tracked repos
      await cleanupTrackedRepos();
      
      // Then scan for any orphaned test repos
      await cleanupTestRepos(GITHUB_TEST_OWNER, 'test-e2e-');
    } catch (error) {
      console.error('[Global Teardown] GitHub cleanup failed:', error);
      // Don't fail the test run due to cleanup issues
    }
  } else {
    console.log('[Global Teardown] GitHub cleanup skipped (not configured)');
  }
  
  console.log('[Global Teardown] Cleanup complete\n');
}

export default globalTeardown;
