import { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Size, HandleDef, CreateNodeOptions } from '../FlowDiagram/core/types';

export class BlockNodeModel extends BaseNode {
  readonly handles: HandleDef[] = [
    { id: 'left', position: 'left' },
    { id: 'right', position: 'right' },
  ];
  readonly minSize: Size = { width: 100, height: 40 };
  readonly maxSize: Size = { width: 400, height: 200 };

  constructor(opts: CreateNodeOptions) {
    super({
      id: opts.id,
      type: 'block',
      position: opts.position,
      size: opts.size ?? { width: 160, height: 80 },
      selected: false,
      data: opts.data,
    });
  }
}
