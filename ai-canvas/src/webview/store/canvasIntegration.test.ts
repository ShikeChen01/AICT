import { describe, it, expect } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import entitiesReducer from './slices/entitiesSlice';
import canvasReducer from './slices/canvasSlice';
import uiReducer from './slices/uiSlice';
import agentReducer from './slices/agentSlice';
import {
  loadEntities,
  addEntity,
  setParent,
  createBucket,
  createModule,
} from './slices/entitiesSlice';
import { setNodePosition, setNodeSize, loadCanvas, setViewport } from './slices/canvasSlice';
import { setDraggedNode, setPotentialParent } from './slices/uiSlice';

function createTestStore() {
  return configureStore({
    reducer: {
      entities: entitiesReducer,
      canvas: canvasReducer,
      ui: uiReducer,
      agent: agentReducer,
    },
  });
}

describe('canvas integration', () => {
  describe('move flow', () => {
    it('loadEntities + loadCanvas + setNodePosition updates nodePositions without throwing', () => {
      const store = createTestStore();
      const b1 = createBucket({ id: 'b1', children: [] });
      const m1 = createModule({ id: 'm1', children: [] });
      store.dispatch(loadEntities([b1, m1]));
      store.dispatch(
        loadCanvas({
          nodePositions: { b1: { x: 0, y: 0 }, m1: { x: 100, y: 100 } },
        })
      );
      store.dispatch(setNodePosition({ id: 'm1', position: { x: 200, y: 150 } }));
      const state = store.getState();
      expect(state.canvas.nodePositions['m1']).toEqual({ x: 200, y: 150 });
    });
  });

  describe('resize flow', () => {
    it('setNodeSize updates nodeSizes without throwing', () => {
      const store = createTestStore();
      const m1 = createModule({ id: 'm1', children: [] });
      store.dispatch(addEntity(m1));
      store.dispatch(setNodeSize({ id: 'm1', size: { width: 240, height: 120 } }));
      const state = store.getState();
      expect(state.canvas.nodeSizes['m1']).toEqual({ width: 240, height: 120 });
    });
  });

  describe('drag-to-parent flow', () => {
    it('setDraggedNode + setPotentialParent + setParent updates parent children without throwing', () => {
      const store = createTestStore();
      const bucket = createBucket({ id: 'bucket1', children: [] });
      const mod = createModule({ id: 'mod1', children: [] });
      store.dispatch(loadEntities([bucket, mod]));
      store.dispatch(
        loadCanvas({
          nodePositions: { [bucket.id]: { x: 0, y: 0 }, [mod.id]: { x: 50, y: 50 } },
        })
      );
      store.dispatch(setDraggedNode(mod.id));
      store.dispatch(setPotentialParent(bucket.id));
      store.dispatch(setParent({ childId: mod.id, parentId: bucket.id }));
      store.dispatch(setDraggedNode(null));
      store.dispatch(setPotentialParent(null));
      const state = store.getState();
      expect(state.entities.byId[bucket.id].children).toContain(mod.id);
      expect(state.ui.draggedNodeId).toBeNull();
      expect(state.ui.potentialParentId).toBeNull();
    });
  });

  describe('drag without reparent', () => {
    it('setDraggedNode + setPotentialParent(null) + no setParent leaves parent unchanged', () => {
      const store = createTestStore();
      const mod = createModule({ id: 'mod1', children: [] });
      const bucket = createBucket({ id: 'bucket1', children: [mod.id] });
      store.dispatch(loadEntities([bucket, mod]));
      store.dispatch(setDraggedNode(mod.id));
      store.dispatch(setPotentialParent(null));
      store.dispatch(setDraggedNode(null));
      store.dispatch(setPotentialParent(null));
      const state = store.getState();
      expect(state.entities.byId[bucket.id].children).toContain(mod.id);
    });
  });

  describe('viewport', () => {
    it('setViewport updates viewport without throwing', () => {
      const store = createTestStore();
      store.dispatch(setViewport({ x: -50, y: -25, zoom: 1.2 }));
      const state = store.getState();
      expect(state.canvas.viewport).toEqual({ x: -50, y: -25, zoom: 1.2 });
    });
  });
});
