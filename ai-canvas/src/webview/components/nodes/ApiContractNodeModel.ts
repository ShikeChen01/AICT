import { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Size, HandleDef, CreateNodeOptions } from '../FlowDiagram/core/types';

export class ApiContractNodeModel extends BaseNode {
  readonly handles: HandleDef[] = [
    { id: 'left', position: 'left' },
    { id: 'right', position: 'right' },
  ];
  readonly minSize: Size = { width: 140, height: 80 };
  readonly maxSize: Size = { width: 400, height: 200 };

  constructor(opts: CreateNodeOptions) {
    super({
      id: opts.id,
      type: 'api_contract',
      position: opts.position,
      size: opts.size ?? { width: 180, height: 100 },
      selected: false,
      data: opts.data,
    });
  }
}
