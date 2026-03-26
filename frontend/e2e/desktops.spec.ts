import { expect, test } from '@playwright/test';

import { setupAuth } from './fixtures/auth';
import { mockWorkspaceAPIs } from './fixtures/api-mocks';
import { MOCK_PROJECT_ID, MOCK_AGENT_IDS, mockDesktops, mockSandbox } from './fixtures/mock-data';
import { DesktopsPage } from './pages/desktops.page';

test.describe('Desktops Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID);
    await setupAuth(page);
  });

  // ── Grid View ───────────────────────────────────────────────

  test('displays page heading and desktop count', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    await expect(desktops.heading).toBeVisible();
    await expect(desktops.newDesktopButton).toBeVisible();
  });

  test('renders desktop cards in grid', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Default mock has 2 desktops
    const count = await desktops.getDesktopCount();
    expect(count).toBe(2);
  });

  test('shows empty state when no desktops', async ({ page }) => {
    await mockWorkspaceAPIs(page, MOCK_PROJECT_ID, { sandboxes: [] });
    await setupAuth(page);

    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    await expect(desktops.emptyState).toBeVisible();
  });

  test('desktop cards show status badges', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Desktop 1 is idle, Desktop 2 is assigned
    await expect(page.locator('text=idle').first()).toBeVisible();
    await expect(page.locator('text=assigned').first()).toBeVisible();
  });

  test('assigned desktop shows agent name', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Desktop 2 is assigned to Engineer Jr
    await expect(page.locator('text=Engineer Jr').first()).toBeVisible();
  });

  // ── New Desktop Creation ────────────────────────────────────

  test('new desktop button creates a desktop', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Intercept the POST request
    const createPromise = page.waitForRequest((req) =>
      req.url().includes('/api/v1/sandboxes') && req.method() === 'POST'
    );

    await desktops.newDesktopButton.click();
    const request = await createPromise;
    const body = request.postDataJSON();
    expect(body.requires_desktop).toBe(true);
  });

  // ── Expanded VNC View ──────────────────────────────────────

  test('clicking desktop card expands to VNC view', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Click the expand icon on first card
    const firstCard = desktops.getCard(0);
    await firstCard.locator('button').filter({ has: page.locator('svg') }).first().click();

    // Should show the expanded view with Back to Grid button
    await expect(desktops.backToGridButton).toBeVisible();
  });

  test('expanded view has interactive/view-only toggle', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);
    await firstCard.locator('button').filter({ has: page.locator('svg') }).first().click();

    await expect(desktops.backToGridButton).toBeVisible();
    // The expanded view top-bar has an Interactive/View Only toggle button
    await expect(page.locator('button:has-text("Interactive"), button:has-text("View Only")').first()).toBeVisible();
  });

  test('back to grid button returns to grid view', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);
    await firstCard.locator('button').filter({ has: page.locator('svg') }).first().click();

    await expect(desktops.backToGridButton).toBeVisible();
    await desktops.backToGridButton.click();

    // Should be back on grid
    await expect(desktops.heading).toBeVisible();
  });

  // ── Agent Assignment ────────────────────────────────────────

  test('idle desktop shows assign to agent button', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Desktop 1 is idle — should show "Assign to agent…"
    const firstCard = desktops.getCard(0);
    await expect(firstCard.locator('text=Assign to agent')).toBeVisible();
  });

  test('assigning agent triggers API call', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);

    // Click "Assign to agent…" to open custom dropdown
    await firstCard.locator('button:has-text("Assign to agent")').click();

    const assignPromise = page.waitForRequest((req) =>
      req.url().includes('/assign') && req.method() === 'POST'
    );

    // Click one of the agent options in the popup
    await page.locator('.z-20 button').first().click();
    const request = await assignPromise;
    expect(request.postDataJSON()).toHaveProperty('agent_id');
  });

  // ── Desktop Actions ────────────────────────────────────────

  test('restart button sends restart request', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);

    const restartPromise = page.waitForRequest((req) =>
      req.url().includes('/restart') && req.method() === 'POST'
    );

    // Find and click the restart button (RotateCcw icon)
    await firstCard.getByRole('button').filter({ has: page.locator('svg.lucide-rotate-ccw') }).click();
    await restartPromise;
  });

  test('destroy button sends delete request', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);

    const destroyPromise = page.waitForRequest((req) =>
      req.url().includes('/sandboxes/') && req.method() === 'DELETE'
    );

    // Find and click the destroy button (Trash2 icon)
    await firstCard.getByRole('button').filter({ has: page.locator('svg.lucide-trash-2') }).click();
    await destroyPromise;
  });

  // ── Config Modal ────────────────────────────────────────────

  test('configure button opens config modal', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    const firstCard = desktops.getCard(0);

    // Find and click the configure button (title="Configure")
    await firstCard.locator('button[title="Configure"]').click();

    // Config modal should be visible with heading and Apply button
    await expect(page.locator('text=Configure:')).toBeVisible();
    await expect(page.locator('text=Apply Config')).toBeVisible();
    await expect(page.locator('text=Desktop Config')).toBeVisible();
  });

  // ── Usage Display ──────────────────────────────────────────

  test('shows remaining desktop hours', async ({ page }) => {
    const desktops = new DesktopsPage(page);
    await desktops.goto(MOCK_PROJECT_ID);
    await desktops.waitForLoad();

    // Should show billing info (headless/desktop remaining)
    await expect(page.locator('text=/remaining/i').first()).toBeVisible();
  });

  // ── Route Redirect ────────────────────────────────────────

  test('/sandbox redirects to /desktops', async ({ page }) => {
    await page.goto(`/project/${MOCK_PROJECT_ID}/sandbox`);
    await page.waitForURL(`**/project/${MOCK_PROJECT_ID}/desktops`);
  });
});
