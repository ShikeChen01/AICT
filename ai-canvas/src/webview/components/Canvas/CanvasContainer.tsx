import React, { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Controls,
  MiniMap,
  Background,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { selectVisibleEntities } from '../../store/selectors/scopeSelectors';
import { selectSelectedIds } from '../../store/selectors/scopeSelectors';
import { setNodePosition, setViewport } from '../../store/slices/canvasSlice';
import { setSelection, enterScope, setContextMenuWithPosition } from '../../store/slices/uiSlice';
import type { EntityId } from '../../../shared/types/entities';
import type { BucketNodeData, ModuleNodeData, BlockNodeData } from '../../../shared/types/canvas';
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
  const selected = selectedIds.includes(entity.id);

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
  const edgesFromState = useAppSelector((s) => s.canvas.edges);
  const byId = useAppSelector((s) => s.entities.byId);
  const viewport = useAppSelector((s) => s.canvas.viewport);

  const visibleIds = useMemo(() => new Set(visibleEntities.map((e) => e.id)), [visibleEntities]);

  const nodes: Node[] = useMemo(() => {
    return visibleEntities.map((entity) => {
      const position = nodePositions[entity.id] ?? { x: 0, y: 0 };
      const data = buildNodeData(entity, selectedIds, byId, edgesFromState);
      return {
        id: entity.id,
        type: entity.type,
        position,
        data,
        selected: selectedIds.includes(entity.id),
      };
    });
  }, [visibleEntities, nodePositions, selectedIds, byId, edgesFromState]);

  const flowEdges: Edge[] = useMemo(() => {
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
      }
    },
    [dispatch]
  );

  const onEdgesChange: OnEdgesChange = useCallback(() => {}, []);

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

  return (
    <ReactFlow
      nodes={nodes}
      edges={flowEdges}
      defaultViewport={{ x: viewport.x, y: viewport.y, zoom: viewport.zoom }}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      onNodeDoubleClick={onNodeDoubleClick}
      onNodeContextMenu={onNodeContextMenu}
      onPaneClick={onPaneClick}
      onMove={(_e, viewport) => onViewportChange(viewport)}
      onMoveEnd={(_e, viewport) => onViewportChange(viewport)}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
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
    <ReactFlowProvider>
      <div style={{ width: '100%', height: '100%' }}>
        <CanvasInner />
      </div>
    </ReactFlowProvider>
  );
}
