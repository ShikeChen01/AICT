import { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Size, HandleDef, CreateNodeOptions } from '../FlowDiagram/core/types';

export class BucketNodeModel extends BaseNode {
  readonly handles: HandleDef[] = [
    { id: 'left', position: 'left' },
    { id: 'right', position: 'right' },
  ];
  readonly minSize: Size = { width: 200, height: 150 };
  readonly maxSize: Size = { width: 600, height: 500 };

  constructor(opts: CreateNodeOptions) {
    super({
      id: opts.id,
      type: 'bucket',
      position: opts.position,
      size: opts.size ?? { width: 280, height: 200 },
      selected: false,
      data: opts.data,
    });
  }
}
