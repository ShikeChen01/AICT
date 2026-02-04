import { describe, it, expect } from 'vitest';
import canvasReducer, {
  setNodePosition,
  setNodeSize,
  setViewport,
  loadCanvas,
} from './canvasSlice';
import type { CanvasState } from './canvasSlice';
import type { EntityId } from '../../../shared/types/entities';

const initialState: CanvasState = {
  nodePositions: {},
  nodeSizes: {},
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
};

describe('canvasSlice', () => {
  describe('setNodePosition', () => {
    it('sets position for a node', () => {
      const state = canvasReducer(initialState, setNodePosition({ id: 'e1', position: { x: 10, y: 20 } }));
      expect(state.nodePositions['e1']).toEqual({ x: 10, y: 20 });
    });

    it('overwrites existing position', () => {
      let state = canvasReducer(initialState, setNodePosition({ id: 'e1', position: { x: 0, y: 0 } }));
      state = canvasReducer(state, setNodePosition({ id: 'e1', position: { x: 100, y: 200 } }));
      expect(state.nodePositions['e1']).toEqual({ x: 100, y: 200 });
    });
  });

  describe('setNodeSize', () => {
    it('sets size for a node', () => {
      const state = canvasReducer(
        initialState,
        setNodeSize({ id: 'e1', size: { width: 200, height: 120 } })
      );
      expect(state.nodeSizes['e1']).toEqual({ width: 200, height: 120 });
    });
  });

  describe('setViewport', () => {
    it('updates viewport', () => {
      const state = canvasReducer(
        initialState,
        setViewport({ x: 50, y: 100, zoom: 1.5 })
      );
      expect(state.viewport).toEqual({ x: 50, y: 100, zoom: 1.5 });
    });

    it('merges partial viewport', () => {
      let state = canvasReducer(initialState, setViewport({ x: 10, y: 20 }));
      state = canvasReducer(state, setViewport({ zoom: 2 }));
      expect(state.viewport).toEqual({ x: 10, y: 20, zoom: 2 });
    });
  });

  describe('loadCanvas', () => {
    it('loads nodePositions and nodeSizes', () => {
      const nodePositions: Record<EntityId, { x: number; y: number }> = {
        a: { x: 0, y: 0 },
        b: { x: 200, y: 100 },
      };
      const nodeSizes: Record<EntityId, { width: number; height: number }> = {
        a: { width: 280, height: 140 },
        b: { width: 160, height: 80 },
      };
      const state = canvasReducer(initialState, loadCanvas({ nodePositions, nodeSizes }));
      expect(state.nodePositions).toEqual(nodePositions);
      expect(state.nodeSizes).toEqual(nodeSizes);
    });

    it('loads viewport', () => {
      const viewport = { x: -100, y: -50, zoom: 0.8 };
      const state = canvasReducer(initialState, loadCanvas({ viewport }));
      expect(state.viewport).toEqual(viewport);
    });

    it('handles empty payload without throwing', () => {
      const state = canvasReducer(initialState, loadCanvas({}));
      expect(state.nodePositions).toEqual({});
      expect(state.nodeSizes).toEqual({});
    });
  });
});
