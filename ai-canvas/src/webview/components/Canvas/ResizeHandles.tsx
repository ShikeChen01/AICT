import React from 'react';
import type { Bounds } from '../FlowDiagram/core/types';

interface ResizeHandlesProps {
  bounds: Bounds;
}

const HANDLE_SIZE = 8;

export function ResizeHandles({ bounds }: ResizeHandlesProps) {
  const s = HANDLE_SIZE / 2;
  const handles = [
    { x: bounds.x - s, y: bounds.y - s },
    { x: bounds.x + bounds.width - s, y: bounds.y - s },
    { x: bounds.x - s, y: bounds.y + bounds.height - s },
    { x: bounds.x + bounds.width - s, y: bounds.y + bounds.height - s },
  ];
  return (
    <>
      {handles.map((h, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: h.x,
            top: h.y,
            width: HANDLE_SIZE,
            height: HANDLE_SIZE,
            background: 'var(--color-accent)',
            border: '1px solid var(--color-background)',
            borderRadius: 2,
            pointerEvents: 'none',
          }}
        />
      ))}
    </>
  );
}
