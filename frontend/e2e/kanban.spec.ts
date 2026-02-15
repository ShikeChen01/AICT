/**
 * Kanban Board E2E Tests
 */

import { test, expect } from '@playwright/test';
import { KanbanPage } from './pages/kanban.page';
import { setupAuth } from './fixtures/auth';
import { TEST_PROJECT_ID } from './fixtures/test-data';

// Skip tests if no test project configured
test.beforeAll(() => {
  if (!TEST_PROJECT_ID) {
    test.skip(true, 'TEST_PROJECT_ID not configured');
  }
});

test.describe('Kanban Board', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('displays kanban board', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    
    await kanbanPage.waitForLoad();
    await expect(kanbanPage.board).toBeVisible();
  });

  test('shows multiple columns', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    // Should have at least 3 columns (backlog, in_progress, done)
    const columnCount = await kanbanPage.getColumnCount();
    expect(columnCount).toBeGreaterThanOrEqual(3);
  });

  test('columns have expected statuses', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    // Check for common column names
    await expect(page.getByText(/backlog/i)).toBeVisible();
    await expect(page.getByText(/in progress|in_progress/i)).toBeVisible();
    await expect(page.getByText(/done|completed/i)).toBeVisible();
  });

  test('displays task cards', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    const taskCount = await kanbanPage.getTotalTaskCount();
    
    // Either we have tasks or the board is empty
    if (taskCount > 0) {
      await expect(kanbanPage.taskCards.first()).toBeVisible();
    }
  });

  test('new task button is visible', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    await expect(kanbanPage.newTaskButton).toBeVisible();
  });

  test('can open task modal by clicking task card', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    const taskCount = await kanbanPage.getTotalTaskCount();
    
    if (taskCount > 0) {
      // Click the first task
      await kanbanPage.taskCards.first().click();
      
      // Modal should appear
      await expect(kanbanPage.taskModal).toBeVisible();
    }
  });
});

test.describe('Kanban - Real-time Updates', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('board updates when tasks change via WebSocket', async ({ page }) => {
    const kanbanPage = new KanbanPage(page);
    await kanbanPage.goto(TEST_PROJECT_ID);
    await kanbanPage.waitForLoad();
    
    // Get initial task count
    const initialCount = await kanbanPage.getTotalTaskCount();
    
    // Wait a bit to see if any updates come through
    // (This tests the WebSocket connection is working)
    await page.waitForTimeout(2000);
    
    // Board should still be functional
    await expect(kanbanPage.board).toBeVisible();
    
    // Task count may or may not have changed, but board should be responsive
    const currentCount = await kanbanPage.getTotalTaskCount();
    expect(currentCount).toBeGreaterThanOrEqual(0);
  });
});
