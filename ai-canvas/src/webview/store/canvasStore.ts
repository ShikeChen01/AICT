import { create } from "zustand";
import type { Edge, Node } from "reactflow";

export type CanvasState = {
  nodes: Node[];
  edges: Edge[];
};

export type CanvasActions = {
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void;
};

export const useCanvasStore = create<CanvasState & CanvasActions>((set) => ({
  nodes: [],
  edges: [],
  setNodes: (updater) =>
    set((state) => ({
      nodes: typeof updater === "function" ? updater(state.nodes) : updater,
    })),
  setEdges: (updater) =>
    set((state) => ({
      edges: typeof updater === "function" ? updater(state.edges) : updater,
    })),
}));
