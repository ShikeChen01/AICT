import { describe, it, expect } from 'vitest';
import entitiesReducer, {
  createBucket,
  createModule,
  createBlock,
  addEntity,
  loadEntities,
  setParent,
} from './entitiesSlice';
import type { EntitiesState } from './entitiesSlice';

const emptyState: EntitiesState = {
  byId: {},
  allIds: [],
};

describe('entitiesSlice', () => {
  describe('setParent', () => {
    it('moves child from one parent to another', () => {
      const bucket1 = createBucket({ id: 'b1', name: 'B1', children: ['m1'] });
      const bucket2 = createBucket({ id: 'b2', name: 'B2', children: [] });
      const mod = createModule({ id: 'm1', name: 'M1', children: [] });
      let state = emptyState;
      state = entitiesReducer(state, addEntity(bucket1));
      state = entitiesReducer(state, addEntity(bucket2));
      state = entitiesReducer(state, addEntity(mod));
      expect(state.byId['b1'].children).toContain('m1');
      expect(state.byId['b2'].children).not.toContain('m1');

      state = entitiesReducer(state, setParent({ childId: 'm1', parentId: 'b2' }));
      expect(state.byId['b1'].children).not.toContain('m1');
      expect(state.byId['b2'].children).toContain('m1');
    });

    it('sets parent to null (root) when removing from parent', () => {
      const bucket = createBucket({ id: 'b1', children: ['m1'] });
      const mod = createModule({ id: 'm1', children: [] });
      let state = emptyState;
      state = entitiesReducer(state, addEntity(bucket));
      state = entitiesReducer(state, addEntity(mod));
      state = entitiesReducer(state, setParent({ childId: 'm1', parentId: null }));
      expect(state.byId['b1'].children).not.toContain('m1');
    });

    it('does not throw when parentId does not exist (no-op for add)', () => {
      const mod = createModule({ id: 'm1', children: [] });
      let state = emptyState;
      state = entitiesReducer(state, addEntity(mod));
      state = entitiesReducer(state, setParent({ childId: 'm1', parentId: 'nonexistent' }));
      expect(state.byId['m1']).toBeDefined();
    });

    it('does not throw when childId has no previous parent', () => {
      const bucket = createBucket({ id: 'b1', children: [] });
      const mod = createModule({ id: 'm1', children: [] });
      let state = emptyState;
      state = entitiesReducer(state, addEntity(bucket));
      state = entitiesReducer(state, addEntity(mod));
      state = entitiesReducer(state, setParent({ childId: 'm1', parentId: 'b1' }));
      expect(state.byId['b1'].children).toContain('m1');
    });
  });

  describe('loadEntities', () => {
    it('replaces state with loaded entities', () => {
      const b = createBucket({ id: 'b1' });
      const m = createModule({ id: 'm1' });
      let state = entitiesReducer(emptyState, addEntity(b));
      state = entitiesReducer(state, loadEntities([b, m]));
      expect(state.allIds).toContain('b1');
      expect(state.allIds).toContain('m1');
      expect(Object.keys(state.byId).length).toBe(2);
    });
  });
});
