/**
 * Auto-layout utilities for canvas entities.
 */

import type { Entity, EntityId } from '../../shared/types/entities';

const HORIZONTAL_SPACING = 200;
const VERTICAL_SPACING = 120;

export interface Position {
  x: number;
  y: number;
}

/**
 * Compute grid positions for a list of entities (e.g. visible in current scope).
 */
export function autoLayout(
  entityIds: EntityId[],
  cols: number = 3
): Record<EntityId, Position> {
  const positions: Record<EntityId, Position> = {};
  const startX = 80;
  const startY = 80;
  entityIds.forEach((id, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    positions[id] = {
      x: startX + col * HORIZONTAL_SPACING,
      y: startY + row * VERTICAL_SPACING,
    };
  });
  return positions;
}

/**
 * Layout visible entities when scope changes; keeps existing positions when possible.
 */
export function layoutForScope(
  visibleIds: EntityId[],
  existingPositions: Record<EntityId, Position>
): Record<EntityId, Position> {
  const result: Record<EntityId, Position> = {};
  visibleIds.forEach((id, index) => {
    if (existingPositions[id]) {
      result[id] = existingPositions[id];
    } else {
      const col = index % 3;
      const row = Math.floor(index / 3);
      result[id] = {
        x: 80 + col * HORIZONTAL_SPACING,
        y: 80 + row * VERTICAL_SPACING,
      };
    }
  });
  return result;
}
