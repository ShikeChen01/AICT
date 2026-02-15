/**
 * GitHub cleanup utility for E2E tests.
 * 
 * IMPORTANT: This utility uses GITHUB_TOKEN_TEST which is specifically
 * for test cleanup operations (deleting test repositories).
 * 
 * The application itself uses GITHUB_TOKEN for all operations.
 * GITHUB_TOKEN_TEST should NEVER be used by the application code.
 */

import { Octokit } from '@octokit/rest';

const GITHUB_TOKEN_TEST = process.env.GITHUB_TOKEN_TEST;

/**
 * Get the Octokit client for cleanup operations.
 * Uses GITHUB_TOKEN_TEST specifically for cleanup.
 */
function getCleanupClient(): Octokit {
  if (!GITHUB_TOKEN_TEST) {
    throw new Error(
      'GITHUB_TOKEN_TEST environment variable is required for test cleanup.\n' +
      'This token is used ONLY for deleting test repositories.'
    );
  }
  
  return new Octokit({ auth: GITHUB_TOKEN_TEST });
}

/**
 * Delete a test repository.
 * 
 * @param owner - Repository owner (username or organization)
 * @param repo - Repository name
 */
export async function deleteTestRepo(owner: string, repo: string): Promise<void> {
  const octokit = getCleanupClient();
  
  try {
    await octokit.repos.delete({ owner, repo });
    console.log(`[GitHub Cleanup] Deleted test repo: ${owner}/${repo}`);
  } catch (error: unknown) {
    const err = error as { status?: number; message?: string };
    if (err.status === 404) {
      console.log(`[GitHub Cleanup] Repo ${owner}/${repo} already deleted or not found`);
    } else {
      console.error(`[GitHub Cleanup] Failed to delete ${owner}/${repo}:`, err.message);
      throw error;
    }
  }
}

/**
 * Check if a repository exists.
 * 
 * @param owner - Repository owner
 * @param repo - Repository name
 * @returns true if the repo exists
 */
export async function repoExists(owner: string, repo: string): Promise<boolean> {
  const octokit = getCleanupClient();
  
  try {
    await octokit.repos.get({ owner, repo });
    return true;
  } catch (error: unknown) {
    const err = error as { status?: number };
    if (err.status === 404) {
      return false;
    }
    throw error;
  }
}

/**
 * Clean up all test repositories matching a prefix.
 * 
 * @param owner - Repository owner
 * @param prefix - Prefix to match (default: 'test-e2e-')
 */
export async function cleanupTestRepos(
  owner: string,
  prefix: string = 'test-e2e-'
): Promise<void> {
  const octokit = getCleanupClient();
  
  console.log(`[GitHub Cleanup] Scanning for test repos with prefix: ${prefix}`);
  
  try {
    // List all repos for the user/org
    const { data: repos } = await octokit.repos.listForAuthenticatedUser({
      per_page: 100,
      sort: 'created',
      direction: 'desc',
    });
    
    // Filter to test repos
    const testRepos = repos.filter(r => r.name.startsWith(prefix));
    
    if (testRepos.length === 0) {
      console.log('[GitHub Cleanup] No test repos found to clean up');
      return;
    }
    
    console.log(`[GitHub Cleanup] Found ${testRepos.length} test repos to clean up`);
    
    // Delete each test repo
    for (const repo of testRepos) {
      await deleteTestRepo(owner, repo.name);
    }
    
    console.log('[GitHub Cleanup] Cleanup complete');
  } catch (error: unknown) {
    const err = error as { message?: string };
    console.error('[GitHub Cleanup] Error during cleanup:', err.message);
    throw error;
  }
}

/**
 * Track repos created during tests for cleanup.
 */
const createdRepos: Array<{ owner: string; repo: string }> = [];

/**
 * Register a repo for cleanup after tests.
 */
export function trackRepoForCleanup(owner: string, repo: string): void {
  createdRepos.push({ owner, repo });
}

/**
 * Clean up all tracked repos.
 */
export async function cleanupTrackedRepos(): Promise<void> {
  console.log(`[GitHub Cleanup] Cleaning up ${createdRepos.length} tracked repos`);
  
  for (const { owner, repo } of createdRepos) {
    try {
      await deleteTestRepo(owner, repo);
    } catch {
      // Continue cleanup even if one fails
    }
  }
  
  // Clear the tracked repos
  createdRepos.length = 0;
}
