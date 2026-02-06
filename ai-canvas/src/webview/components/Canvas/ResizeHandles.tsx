import React from 'react';
import type { Bounds } from '../FlowDiagram/core/types';

export type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';

interface ResizeHandlesProps {
  bounds: Bounds;
  onResizePointerDown?: (corner: Corner, e: React.PointerEvent) => void;
}

const HANDLE_SIZE = 10;

const CURSOR_MAP: Record<Corner, string> = {
  'top-left': 'nwse-resize',
  'top-right': 'nesw-resize',
  'bottom-left': 'nesw-resize',
  'bottom-right': 'nwse-resize',
};

export function ResizeHandles({ bounds, onResizePointerDown }: ResizeHandlesProps) {
  const s = HANDLE_SIZE / 2;
  const corners: { corner: Corner; x: number; y: number }[] = [
    { corner: 'top-left', x: bounds.x - s, y: bounds.y - s },
    { corner: 'top-right', x: bounds.x + bounds.width - s, y: bounds.y - s },
    { corner: 'bottom-left', x: bounds.x - s, y: bounds.y + bounds.height - s },
    { corner: 'bottom-right', x: bounds.x + bounds.width - s, y: bounds.y + bounds.height - s },
  ];
  return (
    <>
      {corners.map((h) => (
        <div
          key={h.corner}
          className="resize-handle"
          style={{
            position: 'absolute',
            left: h.x,
            top: h.y,
            width: HANDLE_SIZE,
            height: HANDLE_SIZE,
            background: 'var(--color-background)',
            border: '2px solid var(--color-focus-border)',
            borderRadius: 2,
            cursor: CURSOR_MAP[h.corner],
            pointerEvents: 'all',
            boxSizing: 'border-box',
            zIndex: 20,
          }}
          onPointerDown={(e) => {
            e.stopPropagation();
            onResizePointerDown?.(h.corner, e);
          }}
        />
      ))}
    </>
  );
}
