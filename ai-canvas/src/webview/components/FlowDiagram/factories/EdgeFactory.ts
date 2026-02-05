import type { CreateEdgeOptions, EdgeType } from '../core/types';
import type { BaseEdge } from '../core/BaseEdge';
import type { CanvasEdge } from '../../../../shared/types/canvas';
import { DependencyEdgeModel } from '../../edges/DependencyEdgeModel';
import { ApiEdgeModel } from '../../edges/ApiEdgeModel';

export class EdgeFactory {
  private registry = new Map<EdgeType, new (opts: CreateEdgeOptions) => BaseEdge>();

  constructor() {
    this.registry.set('dependency', DependencyEdgeModel);
    this.registry.set('api', ApiEdgeModel);
  }

  register(type: EdgeType, ctor: new (opts: CreateEdgeOptions) => BaseEdge): void {
    this.registry.set(type, ctor);
  }

  create(options: CreateEdgeOptions): BaseEdge {
    const type = (options.type ?? 'dependency') as EdgeType;
    const Ctor = this.registry.get(type);
    if (!Ctor) throw new Error(`Unknown edge type: ${type}`);
    return new Ctor({ ...options, type });
  }

  createFromState(edges: CanvasEdge[], selectedIds: string[]): BaseEdge[] {
    return edges.map((e) => {
      const edge = this.create({
        id: e.id,
        nodes: e.nodes,
        type: (e.type as EdgeType) ?? 'dependency',
        data: e.data,
      });
      edge.selected = selectedIds.includes(e.id);
      return edge;
    });
  }
}
