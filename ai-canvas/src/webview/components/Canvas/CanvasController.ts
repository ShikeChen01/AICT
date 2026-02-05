/**
 * Orchestrates FlowDiagram hooks and factories. Single entry for canvas interactions.
 */

import { NodeFactory } from '../FlowDiagram/factories/NodeFactory';
import { EdgeFactory } from '../FlowDiagram/factories/EdgeFactory';
import { useNodeDrag } from '../FlowDiagram/hooks/useNodeDrag';
import { useNodeResize } from '../FlowDiagram/hooks/useNodeResize';
import { useConnect } from '../FlowDiagram/hooks/useConnect';
import { useEdgeReconnect } from '../FlowDiagram/hooks/useEdgeReconnect';
import { useViewport } from '../FlowDiagram/hooks/useViewport';
import { useDoubleClick } from '../FlowDiagram/hooks/useDoubleClick';
import { useSelection } from '../FlowDiagram/hooks/useSelection';
import { useCommandRegistry } from '../../commands/useCommandRegistry';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { BaseEdge } from '../FlowDiagram/core/BaseEdge';
import type { EndpointIndex, Position } from '../FlowDiagram/core/types';
import type { Entity } from '../../../shared/types/entities';
import type { CanvasEdge } from '../../../shared/types/canvas';

type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';

export function useCanvasController() {
  const nodeFactory = new NodeFactory();
  const edgeFactory = new EdgeFactory();
  const commandRegistry = useCommandRegistry();

  const { viewport, startPan, onPan, endPan, onWheel, isPanning } =
    useViewport(commandRegistry);
  const { startDrag, onDrag, endDrag, isDragging } = useNodeDrag(
    viewport,
    commandRegistry
  );
  const { startResize, onResize, endResize, isResizing } = useNodeResize(
    viewport,
    commandRegistry
  );
  const {
    startConnect,
    onConnectDrag,
    endConnect,
    cancelConnect,
    dragLine,
    isConnecting,
  } = useConnect(viewport, commandRegistry);
  const {
    startReconnect,
    onReconnectDrag,
    endReconnect,
    cancelReconnect,
    reconnectDragLine,
    isReconnecting,
  } = useEdgeReconnect(viewport, commandRegistry);
  const { handleDoubleClick } = useDoubleClick(commandRegistry);
  const { selectedIds, select, deselect, clearSelection } = useSelection();

  const buildNodes = (
    entities: Record<string, Entity>,
    positions: Record<string, { x: number; y: number }>,
    sizes: Record<string, { width: number; height: number }>
  ): BaseNode[] => {
    return nodeFactory.createFromState(
      entities,
      positions,
      sizes,
      selectedIds
    );
  };

  const buildEdges = (edges: CanvasEdge[]): BaseEdge[] => {
    return edgeFactory.createFromState(edges, selectedIds);
  };

  const findNodeAt = (
    nodes: BaseNode[],
    canvasX: number,
    canvasY: number
  ): BaseNode | null => {
    for (let i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].containsPoint(canvasX, canvasY)) return nodes[i];
    }
    return null;
  };

  const findResizeHandle = (
    node: BaseNode,
    canvasX: number,
    canvasY: number
  ): Corner | null => {
    const handles = node.getResizeHandleBounds();
    const corners: Corner[] = [
      'top-left',
      'top-right',
      'bottom-left',
      'bottom-right',
    ];
    for (let i = 0; i < 4; i++) {
      const h = handles[i];
      if (
        canvasX >= h.x &&
        canvasX <= h.x + h.width &&
        canvasY >= h.y &&
        canvasY <= h.y + h.height
      ) {
        return corners[i];
      }
    }
    return null;
  };

  const handleEdgeEndpointPointerDown = (
    edgeId: string,
    endpointIndex: EndpointIndex,
    nodes: [string, string],
    pos0: Position,
    pos1: Position
  ) => {
    const anchorPos = endpointIndex === 0 ? pos1 : pos0;
    const movingPos = endpointIndex === 0 ? pos0 : pos1;
    startReconnect(edgeId, endpointIndex, nodes, anchorPos, movingPos);
  };

  return {
    commandRegistry,
    nodeFactory,
    edgeFactory,
    buildNodes,
    buildEdges,
    viewport,
    startPan,
    onPan,
    endPan,
    onWheel,
    isPanning,
    startDrag,
    onDrag,
    endDrag,
    isDragging,
    startResize,
    onResize,
    endResize,
    isResizing,
    startConnect,
    onConnectDrag,
    endConnect,
    cancelConnect,
    dragLine,
    isConnecting,
    handleEdgeEndpointPointerDown,
    onReconnectDrag,
    endReconnect,
    cancelReconnect,
    reconnectDragLine,
    isReconnecting,
    handleDoubleClick,
    selectedIds,
    select,
    deselect,
    clearSelection,
    findNodeAt,
    findResizeHandle,
  };
}
