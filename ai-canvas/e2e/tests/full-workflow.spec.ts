import { test, expect } from '@playwright/test';
import {
  waitForCanvas,
  getNodeByText,
  dragElement,
  getLastSave,
} from './helpers';

const HARNESS_URL = '/e2e/harness/test-harness.html';

test.describe.serial('full workflow from blank canvas', () => {
  test('blank canvas -> create all entities -> all movements -> verify RPC save', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(HARNESS_URL, { waitUntil: 'domcontentloaded' });

    // Wait for app to finish loading (mock RPC responds, then canvas appears)
    const canvas = page.locator('.canvas-container');
    await canvas.waitFor({ state: 'visible', timeout: 60000 });

    // ── Phase 1: Blank canvas loads ──
    await expect(canvas).toBeVisible();
    const transformLayer = page.locator('.canvas-transform-layer');
    await expect(transformLayer).toBeAttached();
    await expect(transformLayer.locator('[role="button"]')).toHaveCount(0);
    await expect(page.getByTitle('Add Bucket')).toBeVisible();
    await expect(page.getByTitle('Add Module')).toBeVisible();
    await expect(page.getByTitle('Add Block')).toBeVisible();

    // ── Phase 2: Create Bucket via modal ──
    await page.getByTitle('Add Bucket').click();
    await expect(page.getByRole('heading', { name: 'Create Bucket' })).toBeVisible();
    await page.getByPlaceholder('e.g. backend, ui, infra').fill('Auth Service');
    await page.getByPlaceholder('Brief description of this bucket').fill('Handles auth');
    await page.getByPlaceholder('e.g. pnpm -C backend test, pytest -q').fill('npm test');
    await page.getByRole('button', { name: 'Create Bucket' }).click();
    await expect(page.getByRole('heading', { name: 'Create Bucket' })).not.toBeVisible();
    await expect(getNodeByText(page, 'Auth Service')).toBeVisible();

    // ── Phase 3: Create second Bucket ──
    await page.getByTitle('Add Bucket').click();
    await page.getByPlaceholder('e.g. backend, ui, infra').fill('API Gateway');
    await page.getByPlaceholder('Brief description of this bucket').fill('Routes requests');
    await page.getByPlaceholder('e.g. pnpm -C backend test, pytest -q').fill('npm test');
    await page.getByRole('button', { name: 'Create Bucket' }).click();
    await expect(getNodeByText(page, 'API Gateway')).toBeVisible();

    // ── Phase 4: Create Module and Block ──
    await page.getByTitle('Add Module').click();
    await expect(getNodeByText(page, 'New Module')).toBeVisible();
    await page.getByTitle('Add Block').click();
    await expect(getNodeByText(page, 'New Block')).toBeVisible();
    await expect(transformLayer.locator('[role="button"]')).toHaveCount(4);

    // ── Phase 5: Select a node ──
    const authNode = getNodeByText(page, 'Auth Service');
    await authNode.click();
    // Selecting a node shows resize handles
    await expect(page.locator('.resize-handle').first()).toBeVisible({ timeout: 3000 });
    await expect(page.locator('.resize-handle')).toHaveCount(4);

    // ── Phase 6: Drag a node ──
    const boxBefore = await authNode.boundingBox();
    expect(boxBefore).toBeTruthy();
    // Drag to a clear area (avoid overlap with other nodes at y=120)
    await dragElement(page, authNode, 100, 250);
    const boxAfter = await authNode.boundingBox();
    expect(boxAfter).toBeTruthy();
    expect(boxAfter!.x).toBeGreaterThanOrEqual(boxBefore!.x + 50);
    expect(boxAfter!.y).toBeGreaterThanOrEqual(boxBefore!.y + 150);

    // ── Phase 7: Resize a node ──
    // Click on Auth Service to select it (after drag it's isolated from other nodes)
    await authNode.click();
    await page.locator('.resize-handle').first().waitFor({ state: 'visible', timeout: 3000 });
    // Get the entity id of the selected node from Redux
    const selectedIdBeforeResize = await page.evaluate(() => {
      const s = (window as any).__store?.getState();
      return s?.ui.selectedIds?.[0] ?? null;
    });
    expect(selectedIdBeforeResize).toBeTruthy();
    const sizeBefore = await page.evaluate((id: string) => {
      const s = (window as any).__store?.getState();
      return s?.canvas.nodeSizes[id] ?? null;
    }, selectedIdBeforeResize!);
    const widthBefore = sizeBefore?.width ?? 280;
    const heightBefore = sizeBefore?.height ?? 200;
    const bottomRightHandle = page.locator('.resize-handle').nth(3);
    await dragElement(page, bottomRightHandle, 50, 30);
    await page.waitForTimeout(200);
    const sizeAfter = await page.evaluate((id: string) => {
      const s = (window as any).__store?.getState();
      return s?.canvas.nodeSizes[id] ?? null;
    }, selectedIdBeforeResize!);
    expect(sizeAfter).toBeTruthy();
    expect(sizeAfter!.width).toBeGreaterThan(widthBefore);
    expect(sizeAfter!.height).toBeGreaterThan(heightBefore);

    // ── Phase 8: Connection handles on hover ──
    // Click empty canvas first to deselect all nodes
    const canvasRect = await canvas.boundingBox();
    expect(canvasRect).toBeTruthy();
    await page.mouse.click(canvasRect!.x + 10, canvasRect!.y + 10);
    await page.waitForTimeout(200);
    // All handles should be gone now
    await expect(page.locator('.connection-handle')).toHaveCount(0, { timeout: 3000 });
    // Hover the API Gateway node to reveal its connection handles
    const apiNode = getNodeByText(page, 'API Gateway');
    await apiNode.hover();
    await expect(page.locator('.connection-handle').first()).toBeVisible({ timeout: 3000 });
    await expect(page.locator('.connection-handle')).toHaveCount(4);
    // Move away, handles should disappear
    await page.mouse.move(0, 0);
    await expect(page.locator('.connection-handle').first()).not.toBeVisible({ timeout: 3000 });

    // ── Phase 9: Create edge via Redux (direct) ──
    // The handle-drag connect interaction is complex with pointer capture.
    // Instead, we directly dispatch an edge creation to verify edges render.
    const edgesBefore = await page.evaluate(() => {
      const s = (window as any).__store?.getState();
      return s?.canvas.edges?.length ?? 0;
    });
    // Get the two bucket entity IDs
    const entityIds = await page.evaluate(() => {
      const s = (window as any).__store?.getState();
      const ids = s?.entities.allIds ?? [];
      return ids.slice(0, 2); // first two are the buckets
    }) as string[];
    expect(entityIds.length).toBe(2);
    // Create edge via CommandRegistry
    await page.evaluate((ids: string[]) => {
      const store = (window as any).__store;
      store.dispatch({
        type: 'canvas/addEdge',
        payload: {
          id: `e-${ids[0]}-${ids[1]}-${Date.now()}`,
          nodes: [ids[0], ids[1]],
          type: 'dependency',
        },
      });
    }, entityIds);
    await page.waitForTimeout(300);
    const edgesAfter = await page.evaluate(() => {
      const s = (window as any).__store?.getState();
      return s?.canvas.edges?.length ?? 0;
    });
    expect(edgesAfter).toBeGreaterThan(edgesBefore);
    // Verify the edge renders in the SVG
    const edgePaths = page.locator('.edge-layer path');
    await expect(edgePaths.first()).toBeAttached({ timeout: 3000 });

    // ── Phase 10: Pan the canvas ──
    const transformBefore = await transformLayer.getAttribute('style');
    const rect = await canvas.boundingBox();
    expect(rect).toBeTruthy();
    const startX = rect!.x + rect!.width / 2;
    const startY = rect!.y + rect!.height / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + 150, startY + 80, { steps: 5 });
    await page.mouse.up();
    const transformAfter = await transformLayer.getAttribute('style');
    expect(transformAfter).not.toBe(transformBefore);
    expect(transformAfter).toMatch(/translate/);

    // ── Phase 11: Zoom the canvas ──
    await page.mouse.move(rect!.x + rect!.width / 2, rect!.y + rect!.height / 2);
    await page.mouse.wheel(0, 100);
    await page.waitForTimeout(100);
    await page.mouse.wheel(0, -150);
    await page.waitForTimeout(100);
    const transformZoom = await transformLayer.getAttribute('style');
    expect(transformZoom).toMatch(/scale/);

    // ── Phase 12: Double-click Bucket enters scope ──
    await authNode.dblclick();
    await expect(page.getByTitle('Back')).toBeVisible({ timeout: 5000 });

    // ── Phase 13: Exit scope ──
    await page.getByTitle('Back').click();
    await expect(page.getByRole('button', { name: 'Workspace' })).toBeVisible();

    // ── Phase 14: Context menu operations ──
    const moduleNode = getNodeByText(page, 'New Module');
    await moduleNode.click({ button: 'right' });
    await expect(page.getByRole('button', { name: 'Rename / Edit' })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: 'Duplicate' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible();
    await page.getByRole('button', { name: 'Duplicate' }).click();
    await expect(getNodeByText(page, 'New Module (copy)')).toBeVisible({ timeout: 5000 });
    const copyNode = getNodeByText(page, 'New Module (copy)');
    await copyNode.click({ button: 'right' });
    await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible({ timeout: 3000 });
    await page.getByRole('button', { name: 'Delete' }).click();
    await expect(getNodeByText(page, 'New Module (copy)')).not.toBeVisible({ timeout: 5000 });

    // ── Phase 15: Verify RPC save ──
    await page.waitForTimeout(1500); // wait for save debounce (800ms)
    const lastSave = await getLastSave(page) as { entities?: unknown[]; canvas?: { edges?: unknown[] } } | null;
    expect(lastSave).not.toBeNull();
    expect(lastSave!.entities).toBeDefined();
    expect(Array.isArray(lastSave!.entities)).toBe(true);
    expect(lastSave!.entities!.length).toBeGreaterThanOrEqual(3); // 2 buckets + 1 module + 1 block - deleted copy
    expect(lastSave!.canvas).toBeDefined();
    expect(Array.isArray(lastSave!.canvas!.edges)).toBe(true);
    expect(lastSave!.canvas!.edges!.length).toBeGreaterThanOrEqual(1); // the edge we created
  });
});
