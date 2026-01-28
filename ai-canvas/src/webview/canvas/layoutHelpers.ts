export const snapToGrid = (value: number, gridSize = 16): number =>
  Math.round(value / gridSize) * gridSize;

export const computeBounds = (positions: Array<{ x: number; y: number }>) => {
  if (positions.length === 0) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  }

  return positions.reduce(
    (acc, pos) => ({
      minX: Math.min(acc.minX, pos.x),
      minY: Math.min(acc.minY, pos.y),
      maxX: Math.max(acc.maxX, pos.x),
      maxY: Math.max(acc.maxY, pos.y),
    }),
    { minX: positions[0].x, minY: positions[0].y, maxX: positions[0].x, maxY: positions[0].y },
  );
};
