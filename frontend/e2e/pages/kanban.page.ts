/**
 * Page Object Model for the Kanban board page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class KanbanPage {
  readonly page: Page;
  readonly board: Locator;
  readonly columns: Locator;
  readonly taskCards: Locator;
  readonly newTaskButton: Locator;
  readonly taskModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.board = page.getByTestId('kanban-board');
    this.columns = page.getByTestId('kanban-column');
    this.taskCards = page.getByTestId('task-card');
    this.newTaskButton = page.getByRole('button', { name: /new task|add task/i });
    this.taskModal = page.getByTestId('task-modal');
  }

  /**
   * Navigate to the kanban board for a project.
   */
  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/kanban`);
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for the board to load.
   */
  async waitForLoad(): Promise<void> {
    await expect(this.board).toBeVisible();
  }

  /**
   * Get the number of columns.
   */
  async getColumnCount(): Promise<number> {
    return this.columns.count();
  }

  /**
   * Get tasks in a specific column by status.
   */
  getTasksInColumn(status: string): Locator {
    return this.page
      .getByTestId('kanban-column')
      .filter({ hasText: new RegExp(status, 'i') })
      .locator('[data-testid="task-card"]');
  }

  /**
   * Get total task count.
   */
  async getTotalTaskCount(): Promise<number> {
    return this.taskCards.count();
  }

  /**
   * Click on a task card by title.
   */
  async openTask(title: string): Promise<void> {
    await this.taskCards.filter({ hasText: title }).click();
    await expect(this.taskModal).toBeVisible();
  }

  /**
   * Create a new task.
   */
  async createTask(title: string, description?: string): Promise<void> {
    await this.newTaskButton.click();
    
    // Fill in the task form
    await this.page.getByLabel(/title/i).fill(title);
    if (description) {
      await this.page.getByLabel(/description/i).fill(description);
    }
    
    await this.page.getByRole('button', { name: /create|save/i }).click();
    
    // Wait for the task to appear
    await expect(this.taskCards.filter({ hasText: title })).toBeVisible();
  }

  /**
   * Check if a task exists.
   */
  async hasTask(title: string): Promise<boolean> {
    const card = this.taskCards.filter({ hasText: title });
    return await card.count() > 0;
  }

  /**
   * Wait for a task to appear in a specific column.
   */
  async waitForTaskInColumn(
    taskTitle: string,
    status: string,
    timeout: number = 30000
  ): Promise<void> {
    const column = this.page
      .getByTestId('kanban-column')
      .filter({ hasText: new RegExp(status, 'i') });
    
    await expect(
      column.locator('[data-testid="task-card"]').filter({ hasText: taskTitle })
    ).toBeVisible({ timeout });
  }
}
