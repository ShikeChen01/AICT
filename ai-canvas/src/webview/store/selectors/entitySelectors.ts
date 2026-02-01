/**
 * Selectors for entity data.
 */

import { createSelector } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import type { Entity, EntityId } from '../../../shared/types/entities';

export const selectEntitiesState = (state: RootState) => state.entities;

export const selectEntityById = (state: RootState, id: EntityId): Entity | undefined =>
  state.entities.byId[id];

export const selectAllEntityIds = (state: RootState): EntityId[] =>
  state.entities.allIds;

export const selectAllEntities = createSelector(
  [selectEntitiesState],
  (entitiesState) => entitiesState.allIds.map((id) => entitiesState.byId[id]).filter(Boolean)
);

export const selectTopLevelBuckets = createSelector(
  [selectAllEntities],
  (entities) => {
    const childIds = new Set<EntityId>();
    for (const e of entities) {
      for (const c of e.children) {
        childIds.add(c);
      }
    }
    return entities.filter((e) => e.type === 'bucket' && !childIds.has(e.id));
  }
);

export function getParentId(entities: Entity[], childId: EntityId): EntityId | null {
  for (const e of entities) {
    if (e.children.includes(childId)) return e.id;
  }
  return null;
}

export const selectParentId = (state: RootState, childId: EntityId): EntityId | null => {
  const entities = selectAllEntities(state);
  return getParentId(entities, childId);
};

export const selectChildren = (state: RootState, parentId: EntityId): Entity[] => {
  const entity = state.entities.byId[parentId];
  if (!entity) return [];
  return entity.children
    .map((id) => state.entities.byId[id])
    .filter((e): e is Entity => e != null);
};

export const selectEntityIdsForSave = (state: RootState): Entity[] =>
  selectAllEntities(state);

export const selectStateForSave = createSelector(
  [
    (state: RootState) => selectAllEntities(state),
    (state: RootState) => state.canvas.nodePositions,
    (state: RootState) => state.canvas.edges,
    (state: RootState) => state.canvas.viewport,
  ],
  (entities, nodePositions, edges, viewport) => ({
    entities,
    canvas: {
      nodes: entities.map((e) => ({
        id: e.id,
        position: nodePositions[e.id] ?? { x: 0, y: 0 },
        type: e.type,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
      })),
      viewport,
    },
  })
);
