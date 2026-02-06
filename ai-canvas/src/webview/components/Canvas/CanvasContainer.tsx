import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { useCanvasController } from './CanvasController';
import { NodeLayer } from './NodeLayer';
import { EdgeLayer } from './EdgeLayer';
import { ConnectionLine } from './ConnectionLine';
import { selectVisibleEntities } from '../../store/selectors/scopeSelectors';
import { getTransformStyle, screenToCanvas } from '../FlowDiagram/core/viewportUtils';
import { setContextMenuWithPosition, setDraggedNode, setPotentialParent, enterScope } from '../../store/slices/uiSlice';
import { setParent } from '../../store/slices/entitiesSlice';
import { getParentId } from '../../store/selectors/entitySelectors';
import { findPotentialParent } from '../../utils/collision';
import type { Entity, EntityId } from '../../../shared/types/entities';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { EndpointIndex, Position } from '../FlowDiagram/core/types';
import type { Corner } from './ResizeHandles';

function CanvasInner() {
  const dispatch = useAppDispatch();
  const containerRef = useRef<HTMLDivElement>(null);
  const controller = useCanvasController();
  
  const visibleEntities = useAppSelector(selectVisibleEntities);
  const nodePositions = useAppSelector((s) => s.canvas.nodePositions);
  const nodeSizes = useAppSelector((s) => s.canvas.nodeSizes);
  const edgesFromState = useAppSelector((s) => s.canvas.edges);
  const byId = useAppSelector((s) => s.entities.byId);
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);

  const originalParentRef = useRef<EntityId | null>(null);
  const entitiesArray = useMemo(() => Object.values(byId).filter(Boolean) as Entity[], [byId]);
  
  // Track which interaction mode we're in
  const interactionRef = useRef<{
    type: 'drag' | 'resize' | 'connect' | 'pan' | null;
    nodeId?: string;
    corner?: Corner;
  }>({ type: null });

  // Double-click detection (since pointer capture prevents native dblclick on nodes)
  const lastClickRef = useRef<{ nodeId: string; time: number } | null>(null);

  // Build nodes and edges from state
  const visibleByIdForCanvas = useMemo(() => {
    const result: Record<string, Entity> = {};
    for (const e of visibleEntities) {
      result[e.id] = e;
    }
    return result;
  }, [visibleEntities]);

  const nodes = useMemo(() => 
    controller.buildNodes(visibleByIdForCanvas, nodePositions, nodeSizes),
    [controller, visibleByIdForCanvas, nodePositions, nodeSizes]
  );

  const edges = useMemo(() => 
    controller.buildEdges(edgesFromState),
    [controller, edgesFromState]
  );

  // Keyboard shortcuts for undo/redo
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const isCtrlOrCmd = e.ctrlKey || e.metaKey;
      if (isCtrlOrCmd && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        controller.commandRegistry.undo();
      } else if (isCtrlOrCmd && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        controller.commandRegistry.redo();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [controller.commandRegistry]);

  // Selection handlers
  const handleSelect = useCallback((id: string, additive?: boolean) => {
    controller.select(id, additive);
  }, [controller]);

  const handleDoubleClick = useCallback((id: string) => {
    const entity = byId[id];
    if (entity?.type === 'bucket') {
      dispatch(enterScope({ entityId: id, mode: 'bucket' }));
    } else if (entity?.type === 'module') {
      dispatch(enterScope({ entityId: id, mode: 'module' }));
    }
  }, [byId, dispatch]);

  const handleContextMenu = useCallback((id: string, e: React.MouseEvent) => {
    dispatch(setContextMenuWithPosition({
      entityId: id,
      x: e.clientX,
      y: e.clientY,
    }));
  }, [dispatch]);

  const handleEdgeEndpointPointerDown = useCallback((
    edgeId: string,
    endpointIndex: EndpointIndex,
    edgeNodes: [string, string],
    pos0: Position,
    pos1: Position,
    e: React.PointerEvent
  ) => {
    controller.handleEdgeEndpointPointerDown(edgeId, endpointIndex, edgeNodes, pos0, pos1);
    interactionRef.current = { type: null }; // reconnect is handled separately
  }, [controller]);

  const handleEdgeClick = useCallback((edgeId: string) => {
    controller.select(edgeId);
  }, [controller]);

  const handleHandlePointerDown = useCallback(
    (nodeId: string, handlePos: Position, e: React.PointerEvent) => {
      controller.startConnect(nodeId, handlePos);
      interactionRef.current = { type: 'connect' };
      containerRef.current?.setPointerCapture(e.pointerId);
    },
    [controller]
  );

  const handleResizePointerDown = useCallback(
    (nodeId: string, corner: Corner, e: React.PointerEvent) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return;
      interactionRef.current = { type: 'resize', nodeId, corner };
      controller.startResize(
        nodeId,
        corner,
        {
          x: node.position.x,
          y: node.position.y,
          width: node.size.width,
          height: node.size.height,
        },
        { x: e.clientX, y: e.clientY },
        node.minSize,
        node.maxSize
      );
      containerRef.current?.setPointerCapture(e.pointerId);
    },
    [controller, nodes]
  );

  // Pointer event handlers
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const canvasPos = screenToCanvas(screenX, screenY, controller.viewport);
    
    // Find node under pointer
    const hitNode = controller.findNodeAt(nodes, canvasPos.x, canvasPos.y);
    
    if (hitNode) {
      // Check if clicking on resize handle (only for selected nodes)
      if (hitNode.selected) {
        const corner = controller.findResizeHandle(hitNode, canvasPos.x, canvasPos.y);
        if (corner) {
          interactionRef.current = { type: 'resize', nodeId: hitNode.id, corner };
          controller.startResize(
            hitNode.id,
            corner,
            {
              x: hitNode.position.x,
              y: hitNode.position.y,
              width: hitNode.size.width,
              height: hitNode.size.height,
            },
            { x: e.clientX, y: e.clientY },
            hitNode.minSize,
            hitNode.maxSize
          );
          e.currentTarget.setPointerCapture(e.pointerId);
          return;
        }
      }
      
      // Select and start dragging the node
      controller.select(hitNode.id);
      interactionRef.current = { type: 'drag', nodeId: hitNode.id };
      controller.startDrag(hitNode.id, hitNode.position, { x: e.clientX, y: e.clientY });
      dispatch(setDraggedNode(hitNode.id));
      originalParentRef.current = getParentId(entitiesArray, hitNode.id);
      e.currentTarget.setPointerCapture(e.pointerId);
    } else {
      // Click on empty canvas - start panning
      interactionRef.current = { type: 'pan' };
      controller.startPan({ x: e.clientX, y: e.clientY });
      controller.clearSelection();
      e.currentTarget.setPointerCapture(e.pointerId);
    }
  }, [controller, nodes, dispatch, entitiesArray]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const screenPos = { x: e.clientX, y: e.clientY };
    
    // Handle reconnect drag (from edge endpoints)
    if (controller.isReconnecting()) {
      controller.onReconnectDrag(screenPos);
      return;
    }

    const interaction = interactionRef.current;
    
    if (interaction.type === 'drag' && interaction.nodeId) {
      controller.onDrag(screenPos);
      
      // Update potential parent for drag-and-drop reparenting
      const nodePos = nodePositions[interaction.nodeId] ?? { x: 0, y: 0 };
      const nodeSize = nodeSizes[interaction.nodeId] ?? { width: 160, height: 80 };
      const allNodesWithSizes = visibleEntities.map((e) => ({
        id: e.id,
        position: nodePositions[e.id] ?? { x: 0, y: 0 },
        size: nodeSizes[e.id] ?? { width: 160, height: 80 },
        type: e.type,
      }));
      const potentialParent = findPotentialParent(
        interaction.nodeId,
        nodePos,
        nodeSize,
        allNodesWithSizes,
        byId
      );
      dispatch(setPotentialParent(potentialParent));
    } else if (interaction.type === 'resize') {
      controller.onResize(screenPos);
    } else if (interaction.type === 'pan') {
      controller.onPan(screenPos);
    } else if (interaction.type === 'connect') {
      controller.onConnectDrag(screenPos);
    }
  }, [controller, nodePositions, nodeSizes, visibleEntities, byId, dispatch]);

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const canvasPos = screenToCanvas(screenX, screenY, controller.viewport);
    
    // Handle reconnect end
    if (controller.isReconnecting()) {
      const hitNode = controller.findNodeAt(nodes, canvasPos.x, canvasPos.y);
      controller.endReconnect(hitNode?.id ?? null);
      e.currentTarget.releasePointerCapture(e.pointerId);
      return;
    }

    const interaction = interactionRef.current;
    
    if (interaction.type === 'drag' && interaction.nodeId) {
      const finalPos = nodePositions[interaction.nodeId] ?? { x: 0, y: 0 };
      const startPos = controller.getDragStartPos?.() ?? finalPos;
      const dragMoved = Math.abs(finalPos.x - startPos.x) > 3 || Math.abs(finalPos.y - startPos.y) > 3;
      controller.endDrag(finalPos);
      
      // Handle reparenting
      if (potentialParentId && potentialParentId !== originalParentRef.current) {
        dispatch(setParent({ childId: interaction.nodeId, parentId: potentialParentId }));
      }
      dispatch(setDraggedNode(null));
      dispatch(setPotentialParent(null));
      originalParentRef.current = null;

      // Double-click detection: if the "drag" was really just a click (no movement),
      // check if it's a double-click on the same node
      if (!dragMoved) {
        const now = Date.now();
        if (
          lastClickRef.current &&
          lastClickRef.current.nodeId === interaction.nodeId &&
          now - lastClickRef.current.time < 400
        ) {
          lastClickRef.current = null;
          handleDoubleClick(interaction.nodeId);
        } else {
          lastClickRef.current = { nodeId: interaction.nodeId, time: now };
        }
      } else {
        lastClickRef.current = null;
      }
    } else if (interaction.type === 'resize' && interaction.nodeId) {
      controller.endResize();
    } else if (interaction.type === 'pan') {
      controller.endPan();
    } else if (interaction.type === 'connect') {
      const hitNode = controller.findNodeAt(nodes, canvasPos.x, canvasPos.y);
      controller.endConnect(hitNode?.id ?? null);
    }
    
    interactionRef.current = { type: null };
    e.currentTarget.releasePointerCapture(e.pointerId);
  }, [controller, nodes, nodePositions, nodeSizes, potentialParentId, dispatch]);

  // Wheel handler for zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    controller.onWheel(e.nativeEvent, rect);
  }, [controller]);

  return (
    <div
      ref={containerRef}
      className="canvas-container"
      style={{
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        position: 'relative',
        background: 'var(--color-background)',
        cursor: controller.isPanning() ? 'grabbing' : 'default',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
    >
      {/* Background grid */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundImage: `
            linear-gradient(to right, var(--color-widget-border) 1px, transparent 1px),
            linear-gradient(to bottom, var(--color-widget-border) 1px, transparent 1px)
          `,
          backgroundSize: `${16 * controller.viewport.zoom}px ${16 * controller.viewport.zoom}px`,
          backgroundPosition: `${controller.viewport.x}px ${controller.viewport.y}px`,
          pointerEvents: 'none',
        }}
      />
      
      {/* Transformed canvas content */}
      <div
        className="canvas-transform-layer"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          ...getTransformStyle(controller.viewport),
        }}
      >
        <EdgeLayer
          edges={edges}
          nodes={nodes}
          onEdgeEndpointPointerDown={handleEdgeEndpointPointerDown}
          onEdgeClick={handleEdgeClick}
        />
        <NodeLayer
          nodes={nodes}
          onSelect={handleSelect}
          onDoubleClick={handleDoubleClick}
          onContextMenu={handleContextMenu}
          onHandlePointerDown={handleHandlePointerDown}
          onResizePointerDown={handleResizePointerDown}
        />
      </div>
      
      {/* Connection drag line (in screen space) */}
      {controller.dragLine && (
        <ConnectionLine
          start={controller.dragLine.start}
          end={controller.dragLine.end}
        />
      )}
      
      {/* Reconnect drag line */}
      {controller.reconnectDragLine && (
        <ConnectionLine
          start={controller.reconnectDragLine.anchor}
          end={controller.reconnectDragLine.moving}
        />
      )}
    </div>
  );
}

export function CanvasContainer() {
  return (
    <div style={{ width: '100%', height: '100%' }}>
      <CanvasInner />
    </div>
  );
}
