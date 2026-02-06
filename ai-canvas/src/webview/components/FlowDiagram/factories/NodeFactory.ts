import type { CreateNodeOptions, NodeType, Size } from '../core/types';
import type { BaseNode } from '../core/BaseNode';
import type { Entity } from '../../../../shared/types/entities';
import { BucketNodeModel } from '../../nodes/BucketNodeModel';
import { ModuleNodeModel } from '../../nodes/ModuleNodeModel';
import { BlockNodeModel } from '../../nodes/BlockNodeModel';
import { ApiContractNodeModel } from '../../nodes/ApiContractNodeModel';

const DEFAULT_SIZES: Record<NodeType, Size> = {
  bucket: { width: 280, height: 200 },
  module: { width: 220, height: 160 },
  block: { width: 160, height: 80 },
  api_contract: { width: 180, height: 100 },
};

export class NodeFactory {
  private registry = new Map<NodeType, new (opts: CreateNodeOptions) => BaseNode>();

  constructor() {
    this.registry.set('bucket', BucketNodeModel);
    this.registry.set('module', ModuleNodeModel);
    this.registry.set('block', BlockNodeModel);
    this.registry.set('api_contract', ApiContractNodeModel);
  }

  register(type: NodeType, ctor: new (opts: CreateNodeOptions) => BaseNode): void {
    this.registry.set(type, ctor);
  }

  create(options: CreateNodeOptions): BaseNode {
    const Ctor = this.registry.get(options.type);
    if (!Ctor) throw new Error(`Unknown node type: ${options.type}`);
    const size = options.size ?? DEFAULT_SIZES[options.type];
    return new Ctor({ ...options, size, selected: options.selected ?? false });
  }

  createFromState(
    entities: Record<string, Entity>,
    positions: Record<string, { x: number; y: number }>,
    sizes: Record<string, { width: number; height: number }>,
    selectedIds: string[]
  ): BaseNode[] {
    return Object.values(entities).map((entity) => {
      const type = this.getNodeType(entity);
      const position = positions[entity.id] ?? { x: 0, y: 0 };
      const size = sizes[entity.id] ?? DEFAULT_SIZES[type];
      const selected = selectedIds.includes(entity.id);
      return this.create({
        id: entity.id,
        type,
        position,
        size,
        data: entity,
        selected,
      });
    });
  }

  private getNodeType(entity: Entity): NodeType {
    switch (entity.type) {
      case 'bucket':
        return 'bucket';
      case 'module':
        return 'module';
      case 'block':
        return 'block';
      default:
        return 'block';
    }
  }
}
