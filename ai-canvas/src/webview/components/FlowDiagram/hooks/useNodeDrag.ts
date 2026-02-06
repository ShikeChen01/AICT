import { useCallback, useRef } from 'react';
import { useAppDispatch } from '../../../store/hooks';
import { setNodePosition } from '../../../store/slices/canvasSlice';
import type { CommandRegistry } from '../../../commands/CommandRegistry';
import type { Position, Viewport } from '../core/types';
import { screenToCanvas } from '../core/viewportUtils';

interface DragState {
  nodeId: string;
  startPos: Position;
  startMouse: Position;
}

export function useNodeDrag(
  viewport: Viewport,
  commandRegistry: CommandRegistry
) {
  const dispatch = useAppDispatch();
  const dragRef = useRef<DragState | null>(null);

  const startDrag = useCallback(
    (nodeId: string, nodePos: Position, mouseScreen: Position) => {
      dragRef.current = {
        nodeId,
        startPos: nodePos,
        startMouse: screenToCanvas(mouseScreen.x, mouseScreen.y, viewport),
      };
    },
    [viewport]
  );

  const onDrag = useCallback(
    (mouseScreen: Position) => {
      if (!dragRef.current) return;
      const mouse = screenToCanvas(mouseScreen.x, mouseScreen.y, viewport);
      const dx = mouse.x - dragRef.current.startMouse.x;
      const dy = mouse.y - dragRef.current.startMouse.y;
      const newPos = {
        x: dragRef.current.startPos.x + dx,
        y: dragRef.current.startPos.y + dy,
      };
      dispatch(
        setNodePosition({ id: dragRef.current.nodeId, position: newPos })
      );
    },
    [viewport, dispatch]
  );

  const endDrag = useCallback(
    (finalPosition: Position) => {
      if (dragRef.current) {
        const { nodeId } = dragRef.current;
        commandRegistry.execute({
          type: 'SET_NODE_POSITION',
          payload: { id: nodeId, position: finalPosition },
        });
      }
      dragRef.current = null;
    },
    [commandRegistry]
  );

  return {
    startDrag,
    onDrag,
    endDrag,
    isDragging: () => dragRef.current !== null,
    getDragStartPos: () => dragRef.current?.startPos ?? null,
  };
}
