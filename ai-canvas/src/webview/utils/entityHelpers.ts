/**
 * Entity relationship helpers for parent-child validation.
 */

import type { EntityId } from '../../shared/types/entities';
import type { Entity } from '../../shared/types/entities';

/**
 * Check if potentialDescendantId is a descendant of ancestorId (i.e. ancestor
 * is an ancestor in the containment tree).
 */
export function isDescendant(
  potentialDescendantId: EntityId,
  ancestorId: EntityId,
  entities: Record<EntityId, Entity>
): boolean {
  const checkChildren = (parentId: EntityId): boolean => {
    const parent = entities[parentId];
    if (!parent) return false;

    for (const childId of parent.children) {
      if (childId === potentialDescendantId) return true;
      if (checkChildren(childId)) return true;
    }
    return false;
  };

  return checkChildren(ancestorId);
}
