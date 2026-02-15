/**
 * Page Object Model for the Chat page.
 */

import { Page, Locator, expect } from '@playwright/test';

export class ChatPage {
  readonly page: Page;
  readonly messageInput: Locator;
  readonly sendButton: Locator;
  readonly messageList: Locator;
  readonly gmStatusIndicator: Locator;
  readonly activityFeed: Locator;

  constructor(page: Page) {
    this.page = page;
    this.messageInput = page.getByPlaceholder(/type a message|enter your message/i);
    this.sendButton = page.getByRole('button', { name: /send/i });
    this.messageList = page.getByTestId('message-list');
    this.gmStatusIndicator = page.getByTestId('gm-status');
    this.activityFeed = page.getByTestId('activity-feed');
  }

  /**
   * Navigate to the chat page for a project.
   */
  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/chat`);
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Send a message to the GM.
   */
  async sendMessage(message: string): Promise<void> {
    await this.messageInput.fill(message);
    await this.sendButton.click();
  }

  /**
   * Wait for a user message to appear in the chat.
   */
  async waitForUserMessage(content: string, timeout: number = 5000): Promise<void> {
    await expect(
      this.page.locator('[data-testid="message-user"]').filter({ hasText: content })
    ).toBeVisible({ timeout });
  }

  /**
   * Wait for a GM response message.
   */
  async waitForGmResponse(timeout: number = 30000): Promise<Locator> {
    const gmMessage = this.page.locator('[data-testid="message-gm"]').last();
    await expect(gmMessage).toBeVisible({ timeout });
    return gmMessage;
  }

  /**
   * Wait for the GM response to contain specific text.
   */
  async waitForGmResponseContaining(
    text: string | RegExp,
    timeout: number = 30000
  ): Promise<void> {
    const gmMessage = this.page.locator('[data-testid="message-gm"]').last();
    await expect(gmMessage).toContainText(text, { timeout });
  }

  /**
   * Get the GM status text.
   */
  async getGmStatus(): Promise<string | null> {
    return this.gmStatusIndicator.textContent();
  }

  /**
   * Wait for the GM to be available.
   */
  async waitForGmAvailable(timeout: number = 10000): Promise<void> {
    await expect(this.gmStatusIndicator).toContainText(/available/i, { timeout });
  }

  /**
   * Wait for activity feed to show specific content.
   */
  async waitForActivityContent(
    text: string | RegExp,
    timeout: number = 120000
  ): Promise<void> {
    await expect(this.activityFeed).toContainText(text, { timeout });
  }

  /**
   * Get all messages in the chat.
   */
  async getMessages(): Promise<Array<{ role: string; content: string }>> {
    const messages: Array<{ role: string; content: string }> = [];
    
    const userMessages = await this.page.locator('[data-testid="message-user"]').all();
    const gmMessages = await this.page.locator('[data-testid="message-gm"]').all();
    
    for (const msg of userMessages) {
      const content = await msg.textContent();
      messages.push({ role: 'user', content: content || '' });
    }
    
    for (const msg of gmMessages) {
      const content = await msg.textContent();
      messages.push({ role: 'gm', content: content || '' });
    }
    
    return messages;
  }
}
