import { Locator, Page, expect } from '@playwright/test';

export class DesktopsPage {
  readonly page: Page;

  // Header
  readonly heading: Locator;
  readonly subtitle: Locator;
  readonly newDesktopButton: Locator;

  // Grid view
  readonly emptyState: Locator;
  readonly desktopGrid: Locator;
  readonly desktopCards: Locator;

  // Expanded VNC view
  readonly backToGridButton: Locator;
  readonly interactiveToggle: Locator;
  readonly vncContainer: Locator;

  // Config modal
  readonly configModal: Locator;

  constructor(page: Page) {
    this.page = page;

    this.heading = page.getByRole('heading', { name: 'Desktops' });
    this.subtitle = page.locator('text=/\\d+ desktops?/');
    this.newDesktopButton = page.getByRole('button', { name: /New Desktop/i });

    this.emptyState = page.locator('text=No desktops running');
    this.desktopGrid = page.locator('.grid');
    this.desktopCards = page.locator('.grid > div');

    this.backToGridButton = page.locator('text=Back to Grid');
    this.interactiveToggle = page.locator('button:has-text("Interactive"), button:has-text("View Only")');
    this.vncContainer = page.locator('[class*="bg-black"]');

    this.configModal = page.locator('[role="dialog"], .fixed.inset-0');
  }

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/project/${projectId}/desktops`);
  }

  async waitForLoad(): Promise<void> {
    await expect(this.heading).toBeVisible({ timeout: 10000 });
  }

  async getDesktopCount(): Promise<number> {
    return this.desktopCards.count();
  }

  getCard(index: number): Locator {
    return this.desktopCards.nth(index);
  }

  getCardByName(name: string): Locator {
    return this.page.locator(`.grid > div:has-text("${name}")`);
  }

  /** Click the expand button on a desktop card */
  async expandDesktop(index: number): Promise<void> {
    const card = this.getCard(index);
    // Click the thumbnail area or the expand icon
    await card.locator('button, [role="button"], img, canvas').first().click();
  }

  /** Get "Assign to agent…" button on an idle card */
  getAssignButton(cardLocator: Locator): Locator {
    return cardLocator.locator('button:has-text("Assign to agent")');
  }

  /** Get action buttons on a card */
  getConfigureButton(cardLocator: Locator): Locator {
    return cardLocator.getByRole('button', { name: /configure/i });
  }

  getRestartButton(cardLocator: Locator): Locator {
    return cardLocator.getByRole('button', { name: /restart/i });
  }

  getDestroyButton(cardLocator: Locator): Locator {
    return cardLocator.getByRole('button', { name: /destroy/i });
  }

  /** Get status badge text on a card */
  getStatusBadge(cardLocator: Locator): Locator {
    return cardLocator.locator('text=/idle|assigned|resetting|unhealthy/');
  }
}
