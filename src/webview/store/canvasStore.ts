import { create } from "zustand";
import type { Edge, Node, Viewport } from "reactflow";

export interface CanvasState {
  nodes: Node[];
  edges: Edge[];
  viewport: Viewport;
  selection: { nodes: string[]; edges: string[] };
}

export interface CanvasActions {
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setViewport: (viewport: Viewport) => void;
  setSelection: (nodeIds: string[], edgeIds: string[]) => void;
}

const defaultViewport: Viewport = { x: 0, y: 0, zoom: 1 };

export const useCanvasStore = create<CanvasState & CanvasActions>((set) => ({
  nodes: [],
  edges: [],
  viewport: defaultViewport,
  selection: { nodes: [], edges: [] },
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setViewport: (viewport) => set({ viewport }),
  setSelection: (nodes, edges) => set({ selection: { nodes, edges } }),
}));
