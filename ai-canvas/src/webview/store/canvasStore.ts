import { create } from 'zustand';
import type { Node, Edge } from 'reactflow';
import type { Entity } from '../../shared/types/entities';
import type { CanvasLayout } from '../../shared/types/rpc';

const DEFAULT_POSITION = { x: 0, y: 0 };
const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

export interface CanvasState {
  nodes: Node[];
  edges: Edge[];
  viewport: { x: number; y: number; zoom: number };
}

export interface CanvasActions {
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setViewport: (v: { x: number; y: number; zoom: number }) => void;
  syncFromEntities: (entities: Entity[], layout?: CanvasLayout) => void;
  getLayout: () => CanvasLayout;
}

export type CanvasStore = CanvasState & CanvasActions;

function entityToNode(entity: Entity, position: { x: number; y: number }): Node {
  return {
    id: entity.id,
    type: entity.type,
    position,
    data: { label: entity.name, entity }
  };
}

function buildContainmentEdges(entities: Entity[]): Edge[] {
  const edges: Edge[] = [];
  for (const e of entities) {
    for (const childId of e.children) {
      edges.push({
        id: `contain-${e.id}-${childId}`,
        source: e.id,
        target: childId,
        type: 'containment'
      });
    }
  }
  return edges;
}

export const useCanvasStore = create<CanvasStore>((set, get) => ({
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setViewport: (viewport) => set({ viewport }),

  syncFromEntities: (entities, layout) => {
    const positionMap = new Map<string, { x: number; y: number }>();
    if (layout?.nodes?.length) {
      for (const n of layout.nodes) {
        positionMap.set(n.id, n.position);
      }
    }
    let y = 0;
    const nodes: Node[] = [];
    for (const entity of entities) {
      const pos = positionMap.get(entity.id) ?? { x: 0, y: y * (NODE_HEIGHT + 20) };
      if (!positionMap.has(entity.id)) {
        y++;
      }
      nodes.push(entityToNode(entity, pos));
    }
    const edges = buildContainmentEdges(entities);
    set({ nodes, edges });
  },

  getLayout: () => {
    const { nodes, edges, viewport } = get();
    return {
      nodes: nodes.map((n) => ({ id: n.id, position: n.position, type: n.type })),
      edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type })),
      viewport
    };
  }
}));
