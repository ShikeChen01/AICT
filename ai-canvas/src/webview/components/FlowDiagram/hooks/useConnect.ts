import { useCallback, useRef, useState } from 'react';
import type { CommandRegistry } from '../../../commands/CommandRegistry';
import type { Position, Viewport } from '../core/types';
import { screenToCanvas } from '../core/viewportUtils';

interface ConnectState {
  startNodeId: string;
  startPos: Position;
}

export function useConnect(
  viewport: Viewport,
  commandRegistry: CommandRegistry
) {
  const connectRef = useRef<ConnectState | null>(null);
  const [dragLine, setDragLine] = useState<{
    start: Position;
    end: Position;
  } | null>(null);

  const startConnect = useCallback((nodeId: string, handlePos: Position) => {
    connectRef.current = { startNodeId: nodeId, startPos: handlePos };
    setDragLine({ start: handlePos, end: handlePos });
  }, []);

  const onConnectDrag = useCallback(
    (mouseScreen: Position) => {
      if (!connectRef.current) return;
      const end = screenToCanvas(mouseScreen.x, mouseScreen.y, viewport);
      setDragLine({ start: connectRef.current.startPos, end });
    },
    [viewport]
  );

  const endConnect = useCallback(
    (targetNodeId: string | null) => {
      if (
        connectRef.current &&
        targetNodeId &&
        targetNodeId !== connectRef.current.startNodeId
      ) {
        commandRegistry.execute({
          type: 'CREATE_EDGE',
          payload: {
            nodes: [connectRef.current.startNodeId, targetNodeId],
            type: 'dependency',
          },
        });
      }
      connectRef.current = null;
      setDragLine(null);
    },
    [commandRegistry]
  );

  const cancelConnect = useCallback(() => {
    connectRef.current = null;
    setDragLine(null);
  }, []);

  return {
    startConnect,
    onConnectDrag,
    endConnect,
    cancelConnect,
    dragLine,
    isConnecting: () => connectRef.current !== null,
  };
}
