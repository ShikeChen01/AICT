/**
 * Redux slice for Bucket/Module/Block entity data.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type {
  Entity,
  EntityId,
  Bucket,
  Module,
  Block,
  EntityStatus,
} from '../../../shared/types/entities';

function randomId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

const defaultBase = {
  purpose: '',
  exports: [] as string[],
  imports: [] as string[],
  deps: [] as string[],
  children: [] as EntityId[],
  tests: {} as { block_test?: string; module_test?: string },
  size_hint: 'm' as const,
  status: 'todo' as EntityStatus,
};

export function createBucket(overrides: Partial<Bucket> = {}): Bucket {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'bucket',
    name: 'New Bucket',
    ...overrides,
  };
}

export function createModule(overrides: Partial<Module> = {}): Module {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'module',
    name: 'New Module',
    ...overrides,
  };
}

export function createBlock(overrides: Partial<Block> = {}): Block {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'block',
    name: 'New Block',
    path: 'untitled',
    ...overrides,
  };
}

export interface EntitiesState {
  byId: Record<EntityId, Entity>;
  allIds: EntityId[];
}

const initialState: EntitiesState = {
  byId: {},
  allIds: [],
};

function addEntityToState(state: EntitiesState, entity: Entity): void {
  state.byId[entity.id] = entity;
  if (!state.allIds.includes(entity.id)) {
    state.allIds.push(entity.id);
  }
}

function removeEntityFromState(state: EntitiesState, id: EntityId): void {
  delete state.byId[id];
  state.allIds = state.allIds.filter((x) => x !== id);
}

function getParentId(state: EntitiesState, childId: EntityId): EntityId | null {
  for (const entity of Object.values(state.byId)) {
    if (entity.children.includes(childId)) return entity.id;
  }
  return null;
}

const entitiesSlice = createSlice({
  name: 'entities',
  initialState,
  reducers: {
    loadEntities(state, action: PayloadAction<Entity[]>) {
      state.byId = {};
      state.allIds = [];
      for (const entity of action.payload) {
        addEntityToState(state, entity);
      }
    },

    addEntity(state, action: PayloadAction<Entity>) {
      addEntityToState(state, action.payload);
    },

    addEntities(state, action: PayloadAction<Entity[]>) {
      for (const entity of action.payload) {
        addEntityToState(state, entity);
      }
    },

    updateEntity(
      state,
      action: PayloadAction<{ id: EntityId; changes: Partial<Entity> }>
    ) {
      const { id, changes } = action.payload;
      const existing = state.byId[id];
      if (existing) {
        state.byId[id] = { ...existing, ...changes } as Entity;
      }
    },

    removeEntity(state, action: PayloadAction<EntityId>) {
      const id = action.payload;
      const parentId = getParentId(state, id);
      if (parentId && state.byId[parentId]) {
        const parent = state.byId[parentId];
        parent.children = parent.children.filter((c) => c !== id);
      }
      const entity = state.byId[id];
      if (entity) {
        for (const childId of [...entity.children]) {
          removeEntityFromState(state, childId);
        }
      }
      removeEntityFromState(state, id);
    },

    setParent(
      state,
      action: PayloadAction<{ childId: EntityId; parentId: EntityId | null }>
    ) {
      const { childId, parentId } = action.payload;
      const prevParentId = getParentId(state, childId);
      if (prevParentId && state.byId[prevParentId]) {
        const prev = state.byId[prevParentId];
        prev.children = prev.children.filter((c) => c !== childId);
      }
      if (parentId && state.byId[parentId]) {
        const parent = state.byId[parentId];
        if (!parent.children.includes(childId)) {
          parent.children.push(childId);
        }
      }
    },

    duplicateEntity(state, action: PayloadAction<EntityId>) {
      const source = state.byId[action.payload];
      if (!source) return;
      const newEntity: Entity = {
        ...source,
        id: randomId(),
        name: source.name + ' (copy)',
        children: [],
      } as Entity;
      if (source.type === 'block') {
        (newEntity as Block).path = (source as Block).path + ' (copy)';
      }
      addEntityToState(state, newEntity);
    },
  },
});

export const {
  loadEntities,
  addEntity,
  addEntities,
  updateEntity,
  removeEntity,
  setParent,
  duplicateEntity,
} = entitiesSlice.actions;

export default entitiesSlice.reducer;
