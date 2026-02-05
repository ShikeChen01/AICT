import { useCallback, useRef } from 'react';
import { useAppDispatch } from '../../../store/hooks';
import { setNodeSize, setNodePosition } from '../../../store/slices/canvasSlice';
import type { CommandRegistry } from '../../../commands/CommandRegistry';
import type { Position, Size, Viewport } from '../core/types';
import { screenToCanvas } from '../core/viewportUtils';

type Corner =
  | 'top-left'
  | 'top-right'
  | 'bottom-left'
  | 'bottom-right';

interface ResizeState {
  nodeId: string;
  corner: Corner;
  startBounds: { x: number; y: number; width: number; height: number };
  startMouse: Position;
  minSize: Size;
  maxSize: Size;
  currentBounds: { x: number; y: number; width: number; height: number };
}

export function useNodeResize(
  viewport: Viewport,
  commandRegistry: CommandRegistry
) {
  const dispatch = useAppDispatch();
  const resizeRef = useRef<ResizeState | null>(null);

  const startResize = useCallback(
    (
      nodeId: string,
      corner: Corner,
      bounds: { x: number; y: number; width: number; height: number },
      mouseScreen: Position,
      minSize: Size,
      maxSize: Size
    ) => {
      resizeRef.current = {
        nodeId,
        corner,
        startBounds: bounds,
        startMouse: screenToCanvas(mouseScreen.x, mouseScreen.y, viewport),
        minSize,
        maxSize,
        currentBounds: { ...bounds },
      };
    },
    [viewport]
  );

  const onResize = useCallback(
    (mouseScreen: Position) => {
      if (!resizeRef.current) return;
      const {
        nodeId,
        corner,
        startBounds,
        startMouse,
        minSize,
        maxSize,
      } = resizeRef.current;
      const mouse = screenToCanvas(mouseScreen.x, mouseScreen.y, viewport);
      const dx = mouse.x - startMouse.x;
      const dy = mouse.y - startMouse.y;

      let newX = startBounds.x;
      let newY = startBounds.y;
      let newW = startBounds.width;
      let newH = startBounds.height;

      if (corner === 'top-left') {
        newX = startBounds.x + dx;
        newY = startBounds.y + dy;
        newW = startBounds.width - dx;
        newH = startBounds.height - dy;
      } else if (corner === 'top-right') {
        newY = startBounds.y + dy;
        newW = startBounds.width + dx;
        newH = startBounds.height - dy;
      } else if (corner === 'bottom-left') {
        newX = startBounds.x + dx;
        newW = startBounds.width - dx;
        newH = startBounds.height + dy;
      } else {
        newW = startBounds.width + dx;
        newH = startBounds.height + dy;
      }

      newW = Math.max(minSize.width, Math.min(maxSize.width, newW));
      newH = Math.max(minSize.height, Math.min(maxSize.height, newH));

      resizeRef.current.currentBounds = {
        x: newX,
        y: newY,
        width: newW,
        height: newH,
      };

      dispatch(
        setNodeSize({ id: nodeId, size: { width: newW, height: newH } })
      );
      dispatch(
        setNodePosition({ id: nodeId, position: { x: newX, y: newY } })
      );
    },
    [viewport, dispatch]
  );

  const endResize = useCallback(() => {
    if (resizeRef.current) {
      const { nodeId, startBounds, currentBounds } = resizeRef.current;
      if (
        currentBounds.x !== startBounds.x ||
        currentBounds.y !== startBounds.y ||
        currentBounds.width !== startBounds.width ||
        currentBounds.height !== startBounds.height
      ) {
        commandRegistry.execute({
          type: 'BATCH',
          payload: {
            commands: [
              {
                type: 'SET_NODE_POSITION',
                payload: {
                  id: nodeId,
                  position: { x: currentBounds.x, y: currentBounds.y },
                },
              },
              {
                type: 'SET_NODE_SIZE',
                payload: {
                  id: nodeId,
                  size: {
                    width: currentBounds.width,
                    height: currentBounds.height,
                  },
                },
              },
            ],
          },
        });
      }
    }
    resizeRef.current = null;
  }, [commandRegistry]);

  return {
    startResize,
    onResize,
    endResize,
    isResizing: () => resizeRef.current !== null,
  };
}
