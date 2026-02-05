/**
 * Redux slice for canvas state: nodes, edges, viewport.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { EntityId } from '../../../shared/types/entities';
import type {
  Viewport,
  CanvasEdge,
  DependencyEdgeData,
  ApiContract,
} from '../../../shared/types/canvas';

export interface NodePosition {
  x: number;
  y: number;
}

export interface NodeDimensions {
  width: number;
  height: number;
}

export interface CanvasState {
  nodePositions: Record<EntityId, NodePosition>;
  nodeSizes: Record<EntityId, NodeDimensions>;
  edges: CanvasEdge[];
  viewport: Viewport;
}

const defaultViewport: Viewport = {
  x: 0,
  y: 0,
  zoom: 1,
};

const initialState: CanvasState = {
  nodePositions: {},
  nodeSizes: {},
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

    setNodeSize(
      state,
      action: PayloadAction<{ id: EntityId; size: NodeDimensions }>
    ) {
      const { id, size } = action.payload;
      state.nodeSizes[id] = size;
    },

    setViewport(state, action: PayloadAction<Partial<Viewport>>) {
      state.viewport = { ...state.viewport, ...action.payload };
    },

    addEdge(
      state,
      action: PayloadAction<{
        id: string;
        nodes: [EntityId, EntityId];
        type?: 'dependency' | 'api';
        data?: Partial<DependencyEdgeData>;
      }>
    ) {
      const { id, nodes, type = 'dependency', data = {} } = action.payload;
      const existing = state.edges.find((e) => e.id === id);
      if (existing) return;
      state.edges.push({
        id,
        nodes,
        type,
        data: {
          dependencyType: 'depends_on',
          hasApiContract: false,
          ...data,
        },
      });
    },

    updateEdge(
      state,
      action: PayloadAction<{ id: string; nodes: [EntityId, EntityId] }>
    ) {
      const idx = state.edges.findIndex((e) => e.id === action.payload.id);
      if (idx !== -1) {
        state.edges[idx].nodes = action.payload.nodes;
      }
    },

    removeEdge(state, action: PayloadAction<string>) {
      state.edges = state.edges.filter((e) => e.id !== action.payload);
    },

    updateEdgeData(
      state,
      action: PayloadAction<{
        id: string;
        data: Partial<DependencyEdgeData>;
      }>
    ) {
      const { id, data } = action.payload;
      const edge = state.edges.find((e) => e.id === id);
      if (edge?.data) {
        edge.data = { ...edge.data, ...data };
      }
    },

    setEdgeApiContract(
      state,
      action: PayloadAction<{
        id: string;
        apiContract: ApiContract | null;
      }>
    ) {
      const { id, apiContract } = action.payload;
      const edge = state.edges.find((e) => e.id === id);
      if (edge?.data) {
        edge.data.hasApiContract = !!apiContract;
        edge.data.apiContract = apiContract ?? undefined;
      }
    },

    loadCanvas(
      state,
      action: PayloadAction<{
        nodePositions?: Record<EntityId, NodePosition>;
        nodeSizes?: Record<EntityId, NodeDimensions>;
        edges?: CanvasEdge[];
        viewport?: Viewport;
      }>
    ) {
      const { nodePositions, nodeSizes, edges, viewport } = action.payload;
      if (nodePositions) state.nodePositions = nodePositions;
      if (nodeSizes) state.nodeSizes = nodeSizes;
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
        state.edges = layoutEdges.map((e: CanvasEdge | { id: string; source: string; target: string }) =>
          'nodes' in e
            ? e
            : {
                id: e.id,
                nodes: [e.source, e.target] as [EntityId, EntityId],
                type: 'dependency' as const,
                data: {
                  dependencyType: 'depends_on' as const,
                  hasApiContract: false,
                },
              }
        );
      }
      if (viewport) state.viewport = viewport;
    },
  },
});

export const {
  setNodePosition,
  setNodePositions,
  setNodeSize,
  removeNodePosition,
  setViewport,
  addEdge,
  updateEdge,
  removeEdge,
  updateEdgeData,
  setEdgeApiContract,
  loadCanvas,
  syncFromLayout,
} = canvasSlice.actions;

export default canvasSlice.reducer;
