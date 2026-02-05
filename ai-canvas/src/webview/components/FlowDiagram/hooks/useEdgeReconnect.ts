import { useCallback, useRef, useState } from 'react';
import type { CommandRegistry } from '../../../commands/CommandRegistry';
import type {
  Position,
  Viewport,
  EndpointIndex,
} from '../core/types';
import { screenToCanvas } from '../core/viewportUtils';

interface ReconnectState {
  edgeId: string;
  endpointIndex: EndpointIndex;
  anchorNodeId: string;
  anchorPos: Position;
}

export function useEdgeReconnect(
  viewport: Viewport,
  commandRegistry: CommandRegistry
) {
  const reconnectRef = useRef<ReconnectState | null>(null);
  const [dragLine, setDragLine] = useState<{
    anchor: Position;
    moving: Position;
  } | null>(null);

  const startReconnect = useCallback(
    (
      edgeId: string,
      endpointIndex: EndpointIndex,
      currentNodes: [string, string],
      anchorPos: Position,
      movingPos: Position
    ) => {
      const anchorIndex = endpointIndex === 0 ? 1 : 0;
      reconnectRef.current = {
        edgeId,
        endpointIndex,
        anchorNodeId: currentNodes[anchorIndex],
        anchorPos,
      };
      setDragLine({ anchor: anchorPos, moving: movingPos });
    },
    []
  );

  const onReconnectDrag = useCallback(
    (mouseScreen: Position) => {
      if (!reconnectRef.current) return;
      const moving = screenToCanvas(
        mouseScreen.x,
        mouseScreen.y,
        viewport
      );
      setDragLine({
        anchor: reconnectRef.current.anchorPos,
        moving,
      });
    },
    [viewport]
  );

  const endReconnect = useCallback(
    (newNodeId: string | null) => {
      if (
        reconnectRef.current &&
        newNodeId &&
        newNodeId !== reconnectRef.current.anchorNodeId
      ) {
        const { edgeId, endpointIndex, anchorNodeId } = reconnectRef.current;
        const newNodes: [string, string] =
          endpointIndex === 0
            ? [newNodeId, anchorNodeId]
            : [anchorNodeId, newNodeId];
        commandRegistry.execute({
          type: 'UPDATE_EDGE',
          payload: { id: edgeId, nodes: newNodes },
        });
      }
      reconnectRef.current = null;
      setDragLine(null);
    },
    [commandRegistry]
  );

  const cancelReconnect = useCallback(() => {
    reconnectRef.current = null;
    setDragLine(null);
  }, []);

  return {
    startReconnect,
    onReconnectDrag,
    endReconnect,
    cancelReconnect,
    reconnectDragLine: dragLine,
    isReconnecting: () => reconnectRef.current !== null,
  };
}
