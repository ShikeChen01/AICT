/**
 * Abstract base class for all edge types. Edges are bidirectional (nodes tuple).
 */

import type { Position, EndpointIndex } from './types';

export abstract class BaseEdge {
  readonly id: string;
  nodes: [string, string];
  readonly type: string;
  data?: unknown;
  selected: boolean;

  constructor(props: {
    id: string;
    nodes: [string, string];
    type: string;
    data?: unknown;
    selected?: boolean;
  }) {
    this.id = props.id;
    this.nodes = props.nodes;
    this.type = props.type;
    this.data = props.data;
    this.selected = props.selected ?? false;
  }

  getNodeAt(index: EndpointIndex): string {
    return this.nodes[index];
  }

  abstract getPath(pos0: Position, pos1: Position): string;

  getEndpointBounds(
    pos0: Position,
    pos1: Position,
    radius = 6
  ): [{ x: number; y: number; r: number }, { x: number; y: number; r: number }] {
    return [
      { x: pos0.x, y: pos0.y, r: radius },
      { x: pos1.x, y: pos1.y, r: radius },
    ];
  }

  hitTestEndpoint(
    canvasX: number,
    canvasY: number,
    pos0: Position,
    pos1: Position,
    radius = 8
  ): EndpointIndex | null {
    const dist0 = Math.hypot(canvasX - pos0.x, canvasY - pos0.y);
    const dist1 = Math.hypot(canvasX - pos1.x, canvasY - pos1.y);
    if (dist0 <= radius) return 0;
    if (dist1 <= radius) return 1;
    return null;
  }
}
