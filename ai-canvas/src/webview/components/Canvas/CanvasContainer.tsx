import React, { useCallback, useMemo, useRef } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  type NodeMouseHandler,
  type NodeTypes,
  type EdgeTypes,
  ConnectionLineType,
  ConnectionMode,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { selectVisibleEntities } from '../../store/selectors/scopeSelectors';
import { selectSelectedIds } from '../../store/selectors/scopeSelectors';
import { setNodePosition, setNodeSize, setViewport, addEdge } from '../../store/slices/canvasSlice';
import { setSelection, enterScope, setContextMenuWithPosition, setDraggedNode, setPotentialParent } from '../../store/slices/uiSlice';
import { setParent } from '../../store/slices/entitiesSlice';
import { getParentId } from '../../store/selectors/entitySelectors';
import type { Entity } from '../../../shared/types/entities';
import { findPotentialParent } from '../../utils/collision';
import type { EntityId } from '../../../shared/types/entities';
import type { BucketNodeData, ModuleNodeData, BlockNodeData, CanvasNode, CanvasEdge } from '../../../shared/types/canvas';
import type { Bucket, Module as ModuleEntity, Block } from '../../../shared/types/entities';
import { BucketNode, ModuleNode, BlockNode } from '../nodes';
import { DependencyEdge } from '../edges/DependencyEdge';

const nodeTypes = {
  bucket: BucketNode,
  module: ModuleNode,
  block: BlockNode,
};

const edgeTypes = {
  dependency: DependencyEdge,
};

function buildNodeData(
  entity: Bucket | ModuleEntity | Block,
  selectedIds: EntityId[],
  byId: Record<EntityId, import('../../../shared/types/entities').Entity>,
  edgesFromState: { source: string; target: string }[]
): BucketNodeData | ModuleNodeData | BlockNodeData {
  const isInScope = true;
  const isDimmed = false;

  if (entity.type === 'bucket') {
    let modulesCount = 0;
    let blocksCount = 0;
    for (const cid of entity.children) {
      const c = byId[cid];
      if (c?.type === 'module') modulesCount++;
      else if (c?.type === 'block') blocksCount++;
    }
    return {
      entity,
      isInScope,
      isDimmed,
      modulesCount,
      blocksCount,
      progress: { done: 0, total: entity.children.length || 1 },
      activeAgents: 0,
    };
  }

  if (entity.type === 'module') {
    const blocksCount = entity.children.filter((id: EntityId) => byId[id]?.type === 'block').length;
    const depsCount = edgesFromState.filter((e) => e.source === entity.id).length;
    return {
      entity,
      isInScope,
      isDimmed,
      depsCount,
      blocksCount,
      progress: { done: 0, total: blocksCount || 1 },
    };
  }

  const path = (entity as Block).path ?? '';
  const ext = path.split('.').pop() ?? '';
  const fileIcon = ext ? `.${ext}` : '📄';
  return {
    entity,
    isInScope,
    isDimmed,
    fileIcon,
    testPassed: false,
  };
}

function CanvasInner() {
  const dispatch = useAppDispatch();
  const visibleEntities = useAppSelector(selectVisibleEntities);
  const selectedIds = useAppSelector(selectSelectedIds);
  const nodePositions = useAppSelector((s) => s.canvas.nodePositions);
  const nodeSizes = useAppSelector((s) => s.canvas.nodeSizes);
  const edgesFromState = useAppSelector((s) => s.canvas.edges);
  const byId = useAppSelector((s) => s.entities.byId);
  const viewport = useAppSelector((s) => s.canvas.viewport);
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);

  const originalParentRef = useRef<EntityId | null>(null);
  const visibleIds = useMemo(() => new Set(visibleEntities.map((e) => e.id)), [visibleEntities]);

  const entitiesArray = useMemo(() => Object.values(byId).filter(Boolean) as Entity[], [byId]);

  const nodes: CanvasNode[] = useMemo(() => {
    return visibleEntities.map((entity) => {
      const position = nodePositions[entity.id] ?? { x: 0, y: 0 };
      const data = buildNodeData(entity, selectedIds, byId, edgesFromState);
      const size = nodeSizes[entity.id];
      return {
        id: entity.id,
        type: entity.type,
        position,
        data,
        selected: selectedIds.includes(entity.id),
        ...(size && { width: size.width, height: size.height }),
      };
    });
  }, [visibleEntities, nodePositions, nodeSizes, selectedIds, byId, edgesFromState]);

  const flowEdges: CanvasEdge[] = useMemo(() => {
    return edgesFromState.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
    );
  }, [edgesFromState, visibleIds]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          dispatch(
            setNodePosition({
              id: change.id,
              position: change.position,
            })
          );
        }
        if (change.type === 'dimensions' && change.dimensions) {
          console.log('[CanvasContainer] dimensions change:', change.id, change.dimensions);
          dispatch(
            setNodeSize({
              id: change.id,
              size: {
                width: change.dimensions.width,
                height: change.dimensions.height,
              },
            })
          );
        }
      }
    },
    [dispatch]
  );

  const onEdgesChange: OnEdgesChange = useCallback(() => {}, []);

  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (connection.source && connection.target && connection.source !== connection.target) {
        dispatch(addEdge({
          source: connection.source,
          target: connection.target,
        }));
      }
    },
    [dispatch]
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      dispatch(setSelection([node.id]));
    },
    [dispatch]
  );

  const onNodeDoubleClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const entity = byId[node.id];
      if (entity?.type === 'bucket') {
        dispatch(enterScope({ entityId: node.id, mode: 'bucket' }));
      } else if (entity?.type === 'module') {
        dispatch(enterScope({ entityId: node.id, mode: 'module' }));
      }
    },
    [dispatch, byId]
  );

  const onPaneClick = useCallback(() => {
    dispatch(setSelection([]));
  }, [dispatch]);

  const onNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: { id: string }) => {
      event.preventDefault();
      dispatch(
        setContextMenuWithPosition({
          entityId: node.id,
          x: event.clientX,
          y: event.clientY,
        })
      );
    },
    [dispatch]
  );

  const onViewportChange = useCallback(
    (viewport: { x: number; y: number; zoom: number }) => {
      dispatch(setViewport(viewport));
    },
    [dispatch]
  );

  const onNodeDragStart: NodeMouseHandler = useCallback(
    (_event, node) => {
      dispatch(setDraggedNode(node.id));
      const parentId = getParentId(entitiesArray, node.id);
      originalParentRef.current = parentId;
    },
    [dispatch, entitiesArray]
  );

  const onNodeDrag: NodeMouseHandler = useCallback(
    (_event, node) => {
      if (!node.position) return;
      const size = nodeSizes[node.id] ?? { width: 160, height: 80 };
      const allNodesWithSizes: Array<{
        id: EntityId;
        position: { x: number; y: number };
        size: { width: number; height: number };
        type: string;
      }> = visibleEntities.map((e) => ({
        id: e.id,
        position: nodePositions[e.id] ?? { x: 0, y: 0 },
        size: nodeSizes[e.id] ?? { width: 160, height: 80 },
        type: e.type,
      }));
      const potentialParent = findPotentialParent(
        node.id,
        node.position,
        size,
        allNodesWithSizes,
        byId
      );
      dispatch(setPotentialParent(potentialParent));
    },
    [dispatch, nodeSizes, visibleEntities, nodePositions, byId]
  );

  const onNodeDragStop: NodeMouseHandler = useCallback(
    (_event, node) => {
      if (potentialParentId && potentialParentId !== originalParentRef.current) {
        dispatch(setParent({ childId: node.id, parentId: potentialParentId }));
      }
      dispatch(setDraggedNode(null));
      dispatch(setPotentialParent(null));
      originalParentRef.current = null;
    },
    [dispatch, potentialParentId]
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={flowEdges}
      defaultViewport={{ x: viewport.x, y: viewport.y, zoom: viewport.zoom }}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={onNodeClick}
      onNodeDoubleClick={onNodeDoubleClick}
      onNodeContextMenu={onNodeContextMenu}
      onPaneClick={onPaneClick}
      onNodeDragStart={onNodeDragStart}
      onNodeDrag={onNodeDrag}
      onNodeDragStop={onNodeDragStop}
      onMove={(_e, viewport) => onViewportChange(viewport)}
      onMoveEnd={(_e, viewport) => onViewportChange(viewport)}
      nodeTypes={nodeTypes as NodeTypes}
      edgeTypes={edgeTypes as EdgeTypes}
      connectionMode={ConnectionMode.Loose}
      connectionLineType={ConnectionLineType.Bezier}
      connectionLineStyle={{ stroke: 'var(--color-focus-border)', strokeWidth: 2 }}
      nodesDraggable
      nodesConnectable
      elementsSelectable
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.2}
      maxZoom={2}
      defaultEdgeOptions={{
        type: 'dependency',
      }}
      style={{ background: 'var(--color-background)' }}
    >
      <Background color="var(--color-widget-border)" gap={16} />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor="var(--color-description)"
        maskColor="rgba(0,0,0,0.6)"
        style={{ background: 'var(--color-sidebar-background)' }}
      />
    </ReactFlow>
  );
}

export function CanvasContainer() {
  return (
    <div style={{ width: '100%', height: '100%' }}>
      <CanvasInner />
    </div>
  );
}
