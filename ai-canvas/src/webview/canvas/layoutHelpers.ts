const GRID_SIZE = 20;

/**
 * Snap position to grid.
 */
export function snapToGrid(x: number, y: number): [number, number] {
  return [
    Math.round(x / GRID_SIZE) * GRID_SIZE,
    Math.round(y / GRID_SIZE) * GRID_SIZE
  ];
}

/**
 * Compute bounding box for a set of positions.
 */
export function computeBounds(
  positions: Array<{ x: number; y: number }>,
  width: number,
  height: number
): { x: number; y: number; width: number; height: number } {
  if (positions.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of positions) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x + width);
    maxY = Math.max(maxY, p.y + height);
  }
  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY
  };
}
