/**
 * Abstract base class for all node types.
 */

import type { Position, Size, Bounds, HandleDef, HandlePosition } from './types';

export abstract class BaseNode {
  readonly id: string;
  readonly type: string;
  position: Position;
  size: Size;
  selected: boolean;
  data: unknown;

  abstract readonly handles: HandleDef[];
  abstract readonly minSize: Size;
  abstract readonly maxSize: Size;

  constructor(props: {
    id: string;
    type: string;
    position: Position;
    size: Size;
    selected: boolean;
    data: unknown;
  }) {
    this.id = props.id;
    this.type = props.type;
    this.position = props.position;
    this.size = props.size;
    this.selected = props.selected;
    this.data = props.data;
  }

  getBounds(): Bounds {
    return { ...this.position, ...this.size };
  }

  getHandlePosition(handlePos: HandlePosition): Position {
    const { x, y, width, height } = this.getBounds();
    switch (handlePos) {
      case 'top':
        return { x: x + width / 2, y };
      case 'bottom':
        return { x: x + width / 2, y: y + height };
      case 'left':
        return { x, y: y + height / 2 };
      case 'right':
        return { x: x + width, y: y + height / 2 };
    }
  }

  containsPoint(px: number, py: number): boolean {
    const b = this.getBounds();
    return (
      px >= b.x &&
      px <= b.x + b.width &&
      py >= b.y &&
      py <= b.y + b.height
    );
  }

  getResizeHandleBounds(): Bounds[] {
    const b = this.getBounds();
    const s = 8;
    return [
      { x: b.x - s / 2, y: b.y - s / 2, width: s, height: s },
      { x: b.x + b.width - s / 2, y: b.y - s / 2, width: s, height: s },
      { x: b.x - s / 2, y: b.y + b.height - s / 2, width: s, height: s },
      { x: b.x + b.width - s / 2, y: b.y + b.height - s / 2, width: s, height: s },
    ];
  }
}
