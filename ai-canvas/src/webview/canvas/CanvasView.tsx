import React, { useCallback } from "react";
import ReactFlow, { Background, Controls, MiniMap, NodeChange, EdgeChange, applyNodeChanges, applyEdgeChanges } from "reactflow";
import { nodeTypes } from "src/webview/canvas/nodeTypes";
import { edgeTypes } from "src/webview/canvas/edgeTypes";
import { useCanvasStore } from "src/webview/store/canvasStore";
import { useSelectionController } from "src/webview/canvas/selectionController";

export const CanvasView: React.FC = () => {
  const nodes = useCanvasStore((state) => state.nodes);
  const edges = useCanvasStore((state) => state.edges);
  const setNodes = useCanvasStore((state) => state.setNodes);
  const setEdges = useCanvasStore((state) => state.setEdges);
  const selectEntity = useSelectionController();

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((current) => applyNodeChanges(changes, current));
    },
    [setNodes],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((current) => applyEdgeChanges(changes, current));
    },
    [setEdges],
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: { id: string }) => {
      selectEntity(node.id);
    },
    [selectEntity],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      fitView
    >
      <Background gap={24} color="#d8cfc2" />
      <MiniMap />
      <Controls />
    </ReactFlow>
  );
};
