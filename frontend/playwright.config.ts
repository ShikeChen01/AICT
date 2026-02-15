import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';

// Load environment variables from .env.test
dotenv.config({ path: '.env.test' });

/**
 * Playwright configuration for AICT E2E tests.
 * 
 * Run all tests: npm run test:e2e
 * Run with UI: npm run test:e2e:ui
 * Run specific test: npx playwright test github-integration.spec.ts
 */
export default defineConfig({
  testDir: './e2e',
  
  // Run tests in files in parallel
  fullyParallel: true,
  
  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,
  
  // Retry on CI only
  retries: process.env.CI ? 2 : 0,
  
  // Opt out of parallel tests on CI for stability
  workers: process.env.CI ? 1 : undefined,
  
  // Reporter to use
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  
  // Shared settings for all the projects below
  use: {
    // Base URL to use in actions like `await page.goto('/')`
    baseURL: process.env.FRONTEND_URL || 'http://localhost:5173',
    
    // Collect trace when retrying the failed test
    trace: 'on-first-retry',
    
    // Capture screenshot on failure
    screenshot: 'only-on-failure',
    
    // Record video on failure
    video: 'on-first-retry',
  },

  // Configure projects for major browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  // Run local dev servers before starting the tests
  // Only start servers in CI or when START_SERVERS=1
  ...(process.env.CI || process.env.START_SERVERS === '1' ? {
    webServer: [
      {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
      {
        command: 'cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000',
        url: 'http://localhost:8000/health',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
        env: {
          ENV: 'development',
        },
      },
    ],
  } : {}),

  // Global teardown to clean up test resources
  globalTeardown: './e2e/global-teardown.ts',

  // Timeout for each test
  timeout: 60 * 1000,

  // Timeout for expect() assertions
  expect: {
    timeout: 10 * 1000,
  },
});
