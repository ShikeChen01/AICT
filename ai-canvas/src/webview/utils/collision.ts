/**
 * Geometric collision detection for drag-to-parent (finding potential parent nodes).
 */

import type { EntityId } from '../../shared/types/entities';
import type { Entity } from '../../shared/types/entities';
import { isDescendant } from './entityHelpers';

export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function isPointInBounds(
  point: { x: number; y: number },
  bounds: Bounds
): boolean {
  return (
    point.x >= bounds.x &&
    point.x <= bounds.x + bounds.width &&
    point.y >= bounds.y &&
    point.y <= bounds.y + bounds.height
  );
}

export function getNodeCenter(
  position: { x: number; y: number },
  size: { width: number; height: number }
): { x: number; y: number } {
  return {
    x: position.x + size.width / 2,
    y: position.y + size.height / 2,
  };
}

function canBeChild(childType: string, parentType: string): boolean {
  if (parentType === 'bucket') return childType === 'module' || childType === 'block';
  if (parentType === 'module') return childType === 'module' || childType === 'block';
  return false;
}

export interface NodeWithBounds {
  id: EntityId;
  position: { x: number; y: number };
  size: { width: number; height: number };
  type: string;
}

/**
 * Find the best potential parent for a dragged node: the node whose bounds
 * contain the dragged node's center, is a valid parent type, and is not
 * a descendant of the dragged node (no circular ref). Returns smallest
 * valid container by area (most specific).
 */
export function findPotentialParent(
  draggedNodeId: EntityId,
  draggedPosition: { x: number; y: number },
  draggedSize: { width: number; height: number },
  allNodes: NodeWithBounds[],
  entities: Record<EntityId, Entity>
): EntityId | null {
  const center = getNodeCenter(draggedPosition, draggedSize);
  const draggedEntity = entities[draggedNodeId];
  if (!draggedEntity) return null;

  const candidates = allNodes.filter((node) => {
    if (node.id === draggedNodeId) return false;

    const bounds: Bounds = {
      x: node.position.x,
      y: node.position.y,
      width: node.size.width,
      height: node.size.height,
    };

    return isPointInBounds(center, bounds);
  });

  if (candidates.length === 0) return null;

  const validCandidates = candidates.filter((node) => {
    const entity = entities[node.id];
    if (!entity || !canBeChild(draggedEntity.type, entity.type)) return false;
    if (isDescendant(node.id, draggedNodeId, entities)) return false;
    return true;
  });

  if (validCandidates.length === 0) return null;

  return validCandidates.reduce((smallest, current) => {
    const smallestArea = smallest.size.width * smallest.size.height;
    const currentArea = current.size.width * current.size.height;
    return currentArea < smallestArea ? current : smallest;
  }).id;
}
