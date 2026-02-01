/**
 * Redux slice for ReactFlow canvas state: nodes, edges, viewport.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { Node, Edge } from 'reactflow';
import type { EntityId } from '../../../shared/types/entities';
import type { Viewport, DependencyEdgeData, ApiContract } from '../../../shared/types/canvas';

export interface NodePosition {
  x: number;
  y: number;
}

export interface CanvasState {
  nodePositions: Record<EntityId, NodePosition>;
  edges: Edge<DependencyEdgeData>[];
  viewport: Viewport;
}

const defaultViewport: Viewport = {
  x: 0,
  y: 0,
  zoom: 1,
};

const initialState: CanvasState = {
  nodePositions: {},
  edges: [],
  viewport: defaultViewport,
};

const canvasSlice = createSlice({
  name: 'canvas',
  initialState,
  reducers: {
    setNodePosition(
      state,
      action: PayloadAction<{ id: EntityId; position: NodePosition }>
    ) {
      const { id, position } = action.payload;
      state.nodePositions[id] = position;
    },

    setNodePositions(
      state,
      action: PayloadAction<Record<EntityId, NodePosition>>
    ) {
      state.nodePositions = { ...state.nodePositions, ...action.payload };
    },

    removeNodePosition(state, action: PayloadAction<EntityId>) {
      delete state.nodePositions[action.payload];
    },

    setViewport(state, action: PayloadAction<Partial<Viewport>>) {
      state.viewport = { ...state.viewport, ...action.payload };
    },

    addEdge(
      state,
      action: PayloadAction<{
        source: EntityId;
        target: EntityId;
        data?: Partial<DependencyEdgeData>;
      }>
    ) {
      const { source, target, data = {} } = action.payload;
      const id = `e-${source}-${target}`;
      const existing = state.edges.find((e) => e.id === id);
      if (existing) return;
      state.edges.push({
        id,
        source,
        target,
        type: 'dependency',
        data: {
          dependencyType: 'depends_on',
          hasApiContract: false,
          ...data,
        },
      });
    },

    removeEdge(
      state,
      action: PayloadAction<{ source: EntityId; target: EntityId } | string>
    ) {
      if (typeof action.payload === 'string') {
        state.edges = state.edges.filter((e) => e.id !== action.payload);
        return;
      }
      const { source, target } = action.payload;
      state.edges = state.edges.filter(
        (e) => !(e.source === source && e.target === target)
      );
    },

    updateEdgeData(
      state,
      action: PayloadAction<{
        source: EntityId;
        target: EntityId;
        data: Partial<DependencyEdgeData>;
      }>
    ) {
      const { source, target, data } = action.payload;
      const edge = state.edges.find(
        (e) => e.source === source && e.target === target
      );
      if (edge?.data) {
        edge.data = { ...edge.data, ...data };
      }
    },

    setEdgeApiContract(
      state,
      action: PayloadAction<{
        source: EntityId;
        target: EntityId;
        apiContract: ApiContract | null;
      }>
    ) {
      const { source, target, apiContract } = action.payload;
      const edge = state.edges.find(
        (e) => e.source === source && e.target === target
      );
      if (edge?.data) {
        edge.data.hasApiContract = !!apiContract;
        edge.data.apiContract = apiContract ?? undefined;
      }
    },

    loadCanvas(
      state,
      action: PayloadAction<{
        nodePositions?: Record<EntityId, NodePosition>;
        edges?: Edge<DependencyEdgeData>[];
        viewport?: Viewport;
      }>
    ) {
      const { nodePositions, edges, viewport } = action.payload;
      if (nodePositions) state.nodePositions = nodePositions;
      if (edges) state.edges = edges;
      if (viewport) state.viewport = viewport;
    },

    syncFromLayout(
      state,
      action: PayloadAction<{
        nodes?: Array<{ id: string; position: { x: number; y: number } }>;
        edges?: Array<{ id: string; source: string; target: string }>;
        viewport?: Viewport;
      }>
    ) {
      const { nodes, edges: layoutEdges, viewport } = action.payload;
      if (nodes) {
        for (const n of nodes) {
          state.nodePositions[n.id] = n.position;
        }
      }
      if (layoutEdges) {
        state.edges = layoutEdges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'dependency',
          data: {
            dependencyType: 'depends_on',
            hasApiContract: false,
          },
        }));
      }
      if (viewport) state.viewport = viewport;
    },
  },
});

export const {
  setNodePosition,
  setNodePositions,
  removeNodePosition,
  setViewport,
  addEdge,
  removeEdge,
  updateEdgeData,
  setEdgeApiContract,
  loadCanvas,
  syncFromLayout,
} = canvasSlice.actions;

export default canvasSlice.reducer;
