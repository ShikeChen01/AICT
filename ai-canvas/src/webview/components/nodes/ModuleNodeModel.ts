import { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Size, HandleDef, CreateNodeOptions } from '../FlowDiagram/core/types';

export class ModuleNodeModel extends BaseNode {
  readonly handles: HandleDef[] = [
    { id: 'top', position: 'top' },
    { id: 'right', position: 'right' },
    { id: 'bottom', position: 'bottom' },
    { id: 'left', position: 'left' },
  ];
  readonly minSize: Size = { width: 180, height: 120 };
  readonly maxSize: Size = { width: 500, height: 400 };

  constructor(opts: CreateNodeOptions) {
    super({
      id: opts.id,
      type: 'module',
      position: opts.position,
      size: opts.size ?? { width: 220, height: 160 },
      selected: opts.selected ?? false,
      data: opts.data,
    });
  }
}
