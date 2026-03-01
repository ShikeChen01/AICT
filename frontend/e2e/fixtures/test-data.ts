/**
 * Test data and seed helpers for E2E tests.
 */

// Test project ID - must exist in the database
export const TEST_PROJECT_ID = process.env.TEST_PROJECT_ID || '';

// GitHub test configuration
export const GITHUB_TEST_OWNER = process.env.GITHUB_TEST_OWNER || '';
export const GITHUB_TOKEN_TEST = process.env.GITHUB_TOKEN_TEST || '';

// Build verification configuration
export const GITHUB_TEST_TOKEN = process.env.GITHUB_TEST_TOKEN || '';
export const GITHUB_TEST_REPOSITORY_LINK = process.env.GITHUB_TEST_REPOSITORY_LINK || '';

/**
 * Generate a unique test repo name with timestamp.
 */
export function generateTestRepoName(prefix: string = 'test-e2e'): string {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  return `${prefix}-${timestamp}-${random}`;
}

/**
 * Generate a unique test project name.
 */
export function generateTestProjectName(): string {
  return `E2E Test Project ${Date.now()}`;
}

/**
 * Check if GitHub integration tests are configured.
 */
export function isGitHubTestConfigured(): boolean {
  return !!(GITHUB_TEST_OWNER && GITHUB_TOKEN_TEST && TEST_PROJECT_ID);
}

/**
 * Validate required environment variables for GitHub tests.
 * Throws if any are missing.
 */
export function requireGitHubTestConfig(): void {
  const missing: string[] = [];
  
  if (!GITHUB_TEST_OWNER) missing.push('GITHUB_TEST_OWNER');
  if (!GITHUB_TOKEN_TEST) missing.push('GITHUB_TOKEN_TEST');
  if (!TEST_PROJECT_ID) missing.push('TEST_PROJECT_ID');
  
  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables for GitHub integration tests: ${missing.join(', ')}\n` +
      'Configure these in frontend/.env.test or .env.test.local'
    );
  }
}
