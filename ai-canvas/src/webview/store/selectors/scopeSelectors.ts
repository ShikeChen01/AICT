/**
 * Selectors for scope, focus mode, and visible entities.
 */

import { createSelector } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import type { Entity, EntityId } from '../../../shared/types/entities';
import { selectAllEntities, getParentId } from './entitySelectors';

export const selectScopeEntityId = (state: RootState): EntityId | null =>
  state.ui.scopeEntityId;

export const selectFocusMode = (state: RootState) => state.ui.focusMode;

export const selectSelectedIds = (state: RootState): EntityId[] =>
  state.ui.selectedIds;

export const selectFilters = (state: RootState) => state.ui.filters;

function getAncestorIds(entities: Entity[], entityId: EntityId): EntityId[] {
  const out: EntityId[] = [];
  let currentId: EntityId | null = entityId;
  while (currentId) {
    const parentId = getParentId(entities, currentId);
    if (parentId) {
      out.push(parentId);
      currentId = parentId;
    } else {
      currentId = null;
    }
  }
  return out;
}

export const selectBreadcrumbPath = createSelector(
  [selectAllEntities, selectScopeEntityId],
  (entities, scopeEntityId) => {
    const path: string[] = ['Workspace'];
    if (!scopeEntityId) return path;
    const scopeEntity = entities.find((e) => e.id === scopeEntityId);
    if (!scopeEntity) return path;
    const ancestorIds = getAncestorIds(entities, scopeEntityId).reverse();
    for (const id of ancestorIds) {
      const e = entities.find((x) => x.id === id);
      if (e) path.push(e.name);
    }
    path.push(scopeEntity.name);
    return path;
  }
);

export const selectBreadcrumbLevels = createSelector(
  [selectAllEntities, selectScopeEntityId],
  (entities, scopeEntityId) => {
    const levels: { id: EntityId | null; name: string }[] = [
      { id: null, name: 'Workspace' },
    ];
    if (!scopeEntityId) return levels;
    const scopeEntity = entities.find((e) => e.id === scopeEntityId);
    if (!scopeEntity) return levels;
    const ancestorIds = getAncestorIds(entities, scopeEntityId).reverse();
    for (const id of ancestorIds) {
      const e = entities.find((x) => x.id === id);
      if (e) levels.push({ id: e.id, name: e.name });
    }
    levels.push({ id: scopeEntity.id, name: scopeEntity.name });
    return levels;
  }
);

export const selectVisibleEntityIds = createSelector(
  [selectAllEntities, selectScopeEntityId],
  (entities, scopeEntityId) => {
    if (!scopeEntityId) {
      const childIds = new Set<EntityId>();
      for (const e of entities) {
        for (const c of e.children) childIds.add(c);
      }
      return entities
        .filter((e) => !childIds.has(e.id))
        .map((e) => e.id);
    }
    const scopeEntity = entities.find((e) => e.id === scopeEntityId);
    if (!scopeEntity) return entities.map((e) => e.id);
    const visibleIds = new Set<EntityId>();
    for (const childId of scopeEntity.children) {
      visibleIds.add(childId);
    }
    return entities.filter((e) => visibleIds.has(e.id)).map((e) => e.id);
  }
);

export const selectVisibleEntities = createSelector(
  [selectAllEntities, selectVisibleEntityIds],
  (entities, visibleIds) => {
    const set = new Set(visibleIds);
    return entities.filter((e) => set.has(e.id));
  }
);

export const selectIsEntityInScope = (state: RootState, entityId: EntityId): boolean => {
  const visibleIds = selectVisibleEntityIds(state);
  return visibleIds.includes(entityId);
};
