import { BaseEdge } from '../FlowDiagram/core/BaseEdge';
import type { Position, CreateEdgeOptions } from '../FlowDiagram/core/types';

export class DependencyEdgeModel extends BaseEdge {
  constructor(opts: CreateEdgeOptions) {
    super({
      id: opts.id,
      nodes: opts.nodes,
      type: 'dependency',
      data: opts.data,
    });
  }

  getPath(pos0: Position, pos1: Position): string {
    return `M ${pos0.x} ${pos0.y} L ${pos1.x} ${pos1.y}`;
  }
}
