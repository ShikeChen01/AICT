/**
 * FlowDiagram core types: position, size, viewport, handles, node/edge props.
 */

export interface Position {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

export type HandlePosition = 'top' | 'right' | 'bottom' | 'left';

export interface HandleDef {
  id: string;
  position: HandlePosition;
}

export interface BaseNodeProps {
  id: string;
  type: string;
  position: Position;
  size: Size;
  selected: boolean;
  data: unknown;
}

export interface BaseEdgeProps {
  id: string;
  nodes: [string, string];
  type: string;
  data?: unknown;
}

export type EndpointIndex = 0 | 1;

export type NodeType = 'bucket' | 'module' | 'block' | 'api_contract';

export type EdgeType = 'dependency' | 'api';

export interface CreateNodeOptions {
  id: string;
  type: NodeType;
  position: Position;
  size?: Size;
  data: unknown;
  selected?: boolean;
}

export interface CreateEdgeOptions {
  id: string;
  nodes: [string, string];
  type?: EdgeType;
  data?: unknown;
}
