import React from 'react';
import type { Position } from '../FlowDiagram/core/types';

interface ConnectionLineProps {
  start: Position;
  end: Position;
}

export function ConnectionLine({ start, end }: ConnectionLineProps) {
  return (
    <svg
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    >
      <line
        x1={start.x}
        y1={start.y}
        x2={end.x}
        y2={end.y}
        stroke="var(--color-focus-border)"
        strokeWidth={2}
        strokeDasharray="4,4"
      />
    </svg>
  );
}
