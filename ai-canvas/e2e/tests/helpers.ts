import type { Page, Locator } from '@playwright/test';

/**
 * Wait for the canvas container to be visible (app has loaded).
 */
export async function waitForCanvas(page: Page): Promise<Locator> {
  const canvas = page.locator('.canvas-container');
  await canvas.waitFor({ state: 'visible', timeout: 30000 });
  return canvas;
}

/**
 * Locate a node by its visible text (e.g. "Auth Service", "New Module").
 * Scoped to the canvas transform layer.
 */
export function getNodeByText(page: Page, text: string): Locator {
  return page.locator('.canvas-transform-layer').locator(`[role="button"]:has-text("${text}")`).first();
}

/**
 * Perform a pointer drag: down at element center, move by (dx, dy), up.
 */
export async function dragElement(
  page: Page,
  locator: Locator,
  dx: number,
  dy: number,
  steps = 10
): Promise<void> {
  const box = await locator.boundingBox();
  if (!box) throw new Error('Element has no bounding box');
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps });
  await page.mouse.up();
}

/**
 * Get the RPC log (all postMessage calls) from the mock.
 */
export async function getRpcLog(page: Page): Promise<unknown[]> {
  return page.evaluate(() => (window as Window & { __rpcLog?: unknown[] }).__rpcLog ?? []);
}

/**
 * Get the last saveWorkspaceState params from the mock.
 */
export async function getLastSave(page: Page): Promise<unknown> {
  return page.evaluate(() => (window as Window & { __lastSave?: unknown }).__lastSave ?? null);
}

/**
 * Clear the RPC log (e.g. between assertion phases).
 */
export async function clearRpcLog(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as Window & { __rpcLog?: unknown[] }).__rpcLog = [];
  });
}
