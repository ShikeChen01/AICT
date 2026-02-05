/**
 * Coordinate conversion and viewport transform utilities.
 */

import type { CSSProperties } from 'react';
import type { Position, Viewport } from './types';

export function screenToCanvas(
  screenX: number,
  screenY: number,
  viewport: Viewport
): Position {
  return {
    x: (screenX - viewport.x) / viewport.zoom,
    y: (screenY - viewport.y) / viewport.zoom,
  };
}

export function canvasToScreen(
  canvasX: number,
  canvasY: number,
  viewport: Viewport
): Position {
  return {
    x: canvasX * viewport.zoom + viewport.x,
    y: canvasY * viewport.zoom + viewport.y,
  };
}

export function getTransformStyle(viewport: Viewport): CSSProperties {
  return {
    transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
    transformOrigin: '0 0',
  };
}
