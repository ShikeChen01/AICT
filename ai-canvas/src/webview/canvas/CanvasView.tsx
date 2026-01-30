import React, { useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  applyNodeChanges,
  applyEdgeChanges,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useCanvasStore } from '../store/canvasStore';
import { useAppStore } from '../store/appStore';
import { nodeTypes } from './nodeTypes';
import { edgeTypes } from './edgeTypes';
import { useSelectionController } from './selectionController';

export function CanvasView() {
  const entities = useAppStore((s) => s.entities);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const syncFromEntities = useCanvasStore((s) => s.syncFromEntities);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const onSelectionChange = useSelectionController();

  useEffect(() => {
    syncFromEntities(entities);
  }, [entities, syncFromEntities]);

  const onNodesChange: OnNodesChange = (changes) => {
    setNodes(applyNodeChanges(changes, nodes));
  };
  const onEdgesChange: OnEdgesChange = (changes) => {
    setEdges(applyEdgeChanges(changes, edges));
  };

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onSelectionChange={onSelectionChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        snapToGrid={true}
        snapGrid={[20, 20]}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
