/**
 * WorkflowGraph Component
 * Visualizes the LangGraph workflow (Manager <-> CTO, Manager -> Engineer)
 */

import { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Position,
  MarkerType,
} from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';

import { AgentNode } from './AgentNode';
import { ToolNode } from './ToolNode';
import type { WorkflowUpdateData, AgentRole } from '../../types';

// Node types registration
const nodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
};

// Matches backend/graph/workflow.py: Manager, CTO (advisory), Engineer
const initialNodes: Node[] = [
  {
    id: 'manager',
    type: 'agent',
    position: { x: 0, y: 0 },
    data: { label: 'Manager', role: 'manager' as AgentRole, status: 'idle' },
  },
  {
    id: 'manager_tools',
    type: 'tool',
    position: { x: 0, y: 0 },
    data: { label: 'Manager Tools' },
  },
  {
    id: 'cto',
    type: 'agent',
    position: { x: 0, y: 0 },
    data: { label: 'CTO', role: 'cto' as AgentRole, status: 'idle' },
  },
  {
    id: 'cto_tools',
    type: 'tool',
    position: { x: 0, y: 0 },
    data: { label: 'CTO Tools' },
  },
  {
    id: 'engineer',
    type: 'agent',
    position: { x: 0, y: 0 },
    data: { label: 'Engineer', role: 'engineer' as AgentRole, status: 'idle' },
  },
  {
    id: 'engineer_tools',
    type: 'tool',
    position: { x: 0, y: 0 },
    data: { label: 'Engineer Tools' },
  },
  {
    id: 'end',
    type: 'output',
    position: { x: 0, y: 0 },
    data: { label: 'End' },
    style: { background: '#e5e7eb', border: '2px solid #9ca3af', borderRadius: '50%', width: 60, height: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  },
];

const initialEdges: Edge[] = [
  // Manager edges
  { id: 'e-manager-tools', source: 'manager', target: 'manager_tools', label: 'tools', animated: false },
  { id: 'e-tools-manager', source: 'manager_tools', target: 'manager', animated: false },
  { id: 'e-manager-cto', source: 'manager', target: 'cto', label: 'consult', markerEnd: { type: MarkerType.ArrowClosed } },
  { id: 'e-cto-manager', source: 'cto', target: 'manager', label: 'report', style: { strokeDasharray: '5,5' } },
  { id: 'e-manager-engineer', source: 'manager', target: 'engineer', label: 'assign', style: { strokeDasharray: '5,5' } },
  { id: 'e-manager-end', source: 'manager', target: 'end', label: 'done', markerEnd: { type: MarkerType.ArrowClosed } },
  // CTO edges
  { id: 'e-cto-tools', source: 'cto', target: 'cto_tools', label: 'tools', animated: false },
  { id: 'e-tools-cto', source: 'cto_tools', target: 'cto', animated: false },
  // Engineer edges
  { id: 'e-engineer-tools', source: 'engineer', target: 'engineer_tools', label: 'tools', animated: false },
  { id: 'e-tools-engineer', source: 'engineer_tools', target: 'engineer', animated: false },
  { id: 'e-engineer-manager', source: 'engineer', target: 'manager', label: 'report', markerEnd: { type: MarkerType.ArrowClosed } },
];

// Auto-layout using dagre
function getLayoutedElements(nodes: Node[], edges: Edge[], direction = 'TB') {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 80, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 150, height: 60 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 75,
        y: nodeWithPosition.y - 30,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  return { nodes: layoutedNodes, edges };
}

interface WorkflowGraphProps {
  projectId: string;
  currentNode?: string | null;
  workflowUpdate?: WorkflowUpdateData | null;
  onNodeClick?: (nodeId: string) => void;
}

export function WorkflowGraph({
  currentNode,
  workflowUpdate,
  onNodeClick,
}: WorkflowGraphProps) {
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => getLayoutedElements(initialNodes, initialEdges),
    []
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges);

  // Update node highlighting based on current workflow state
  useEffect(() => {
    const activeNode = workflowUpdate?.current_node || currentNode;
    const previousNode = workflowUpdate?.previous_node;

    setNodes((nds) =>
      nds.map((node) => {
        const isActive = node.id === activeNode;
        const wasActive = node.id === previousNode;

        return {
          ...node,
          data: {
            ...node.data,
            status: isActive ? 'active' : wasActive ? 'completed' : 'idle',
          },
          style: {
            ...node.style,
            boxShadow: isActive ? '0 0 20px rgba(59, 130, 246, 0.5)' : undefined,
          },
        };
      })
    );

    // Animate edges to the current node
    setEdges((eds) =>
      eds.map((edge) => ({
        ...edge,
        animated: edge.target === activeNode,
        style: {
          ...edge.style,
          stroke: edge.target === activeNode ? '#3b82f6' : undefined,
          strokeWidth: edge.target === activeNode ? 2 : 1,
        },
      }))
    );
  }, [currentNode, workflowUpdate, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (onNodeClick && node.type === 'agent') {
        onNodeClick(node.id);
      }
    },
    [onNodeClick]
  );

  return (
    <div className="h-full min-h-[400px] w-full overflow-hidden rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
      >
        <Background color="#d7dee9" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            if (node.data?.status === 'active') return '#3b82f6';
            if (node.data?.status === 'completed') return '#22c55e';
            if (node.type === 'tool') return '#f59e0b';
            return '#6b7280';
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
        />
      </ReactFlow>
    </div>
  );
}

export default WorkflowGraph;
