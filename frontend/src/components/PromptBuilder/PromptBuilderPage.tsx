/**
 * PromptBuilderPage — replaces the Workflow page.
 *
 * Renders a vertical React Flow canvas where each node is a prompt block for
 * the selected agent. Edges connect consecutive blocks in position order.
 * A terminal node at the bottom shows the LLM model that receives the prompt.
 *
 * Interaction architecture:
 *  - Callbacks (onEdit, onToggle, onMoveUp, onMoveDown) live in a React
 *    context so that PromptBlockNode reads them directly via useContext.
 *    This avoids stale-closure issues that arise when functions are embedded
 *    in React Flow node data objects (which React Flow may internally cache).
 *  - AgentConfigPanel floats top-right on the canvas (outside React Flow).
 *  - BlockEditorPanel slides in from the right when a node's edit button is clicked.
 */

import { useEffect, useState, useCallback, useMemo, createContext } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { PromptBlockNode } from './PromptBlockNode';
import { LLMTerminalNode } from './LLMTerminalNode';
import { AgentConfigPanel } from './AgentConfigPanel';
import { BlockEditorPanel } from './BlockEditorPanel';
import { getAgents, listAgentBlocks, saveAgentBlocks } from '../../api/client';
import type { Agent, PromptBlockConfig, PromptBlockConfigItem } from '../../types';

// ── Shared context for node interaction callbacks ──────────────────────────
//
// Callbacks are provided via context rather than node.data so that React Flow's
// internal node memoization cannot stale-cache them. The node component reads
// them with useContext() which always gets the latest reference.

export interface PromptBuilderCallbacks {
  onEdit: (blockId: string) => void;
  onToggle: (blockId: string) => void;
  onMoveUp: (blockId: string) => void;
  onMoveDown: (blockId: string) => void;
}

export const PromptBuilderContext = createContext<PromptBuilderCallbacks>({
  onEdit: () => {},
  onToggle: () => {},
  onMoveUp: () => {},
  onMoveDown: () => {},
});

// ── React Flow node type registration ─────────────────────────────────────
//
// Defined outside the component so the object reference is stable across
// renders — React Flow will re-mount all nodes if nodeTypes changes identity.

const nodeTypes = {
  promptBlock: PromptBlockNode,
  llmTerminal: LLMTerminalNode,
};

// ── Layout constants ───────────────────────────────────────────────────────

const NODE_WIDTH = 256;  // matches w-64 in PromptBlockNode
const NODE_HEIGHT = 148;
const Y_GAP = 60;

// ── Build nodes + edges from block list ───────────────────────────────────
//
// Callbacks are NOT included in node.data — they come from PromptBuilderContext.
// Only the static data the node needs to render is in data (blockId, blockKey,
// content, position, enabled, isFirst, isLast).

function buildGraph(
  blocks: PromptBlockConfig[],
  agent: Agent,
): { nodes: Node[]; edges: Edge[] } {
  const sorted = [...blocks].sort((a, b) => a.position - b.position);
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const xOffset = -(NODE_WIDTH / 2);
  let y = 0;

  sorted.forEach((block, idx) => {
    const nodeId = `block-${block.id}`;

    nodes.push({
      id: nodeId,
      type: 'promptBlock',
      position: { x: xOffset, y },
      data: {
        blockId: block.id,
        blockKey: block.block_key,
        content: block.content,
        position: block.position,
        enabled: block.enabled,
        isFirst: idx === 0,
        isLast: idx === sorted.length - 1,
      },
      draggable: false,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });

    if (idx > 0) {
      const prevBlock = sorted[idx - 1];
      const prevId = `block-${prevBlock.id}`;
      const isDashed = !prevBlock.enabled || !block.enabled;
      edges.push({
        id: `e-${prevId}-${nodeId}`,
        source: prevId,
        target: nodeId,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#9ca3af' },
        style: {
          stroke: '#9ca3af',
          strokeDasharray: isDashed ? '4,4' : undefined,
        },
      });
    }

    y += NODE_HEIGHT + Y_GAP;
  });

  // Terminal (LLM) node
  nodes.push({
    id: 'llm-terminal',
    type: 'llmTerminal',
    position: { x: xOffset, y },
    data: {
      model: agent.model,
      provider: agent.provider,
      thinking_enabled: agent.thinking_enabled,
    },
    draggable: false,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  if (sorted.length > 0) {
    const lastId = `block-${sorted[sorted.length - 1].id}`;
    edges.push({
      id: `e-${lastId}-terminal`,
      source: lastId,
      target: 'llm-terminal',
      markerEnd: { type: MarkerType.ArrowClosed, color: '#7c3aed' },
      style: { stroke: '#7c3aed', strokeWidth: 2 },
      label: 'assembled prompt',
      labelStyle: { fontSize: 11, fill: '#7c3aed' },
    });
  }

  return { nodes, edges };
}

// ── Main Component ─────────────────────────────────────────────────────────

interface PromptBuilderPageProps {
  projectId: string;
}

export function PromptBuilderPage({ projectId }: PromptBuilderPageProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<PromptBlockConfig[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [loadingBlocks, setLoadingBlocks] = useState(false);
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const editingBlock = useMemo(
    () => blocks.find((b) => b.id === editingBlockId) ?? null,
    [blocks, editingBlockId]
  );

  // ── Load agents ──────────────────────────────────────────────────────────

  useEffect(() => {
    setLoadingAgents(true);
    getAgents(projectId)
      .then((list) => {
        setAgents(list);
        if (list.length > 0) setSelectedAgentId(list[0].id);
      })
      .catch(console.error)
      .finally(() => setLoadingAgents(false));
  }, [projectId]);

  // ── Load blocks for selected agent ───────────────────────────────────────

  useEffect(() => {
    if (!selectedAgentId) {
      setBlocks([]);
      return;
    }
    setLoadingBlocks(true);
    setSaveError(null);
    listAgentBlocks(selectedAgentId)
      .then(setBlocks)
      .catch(console.error)
      .finally(() => setLoadingBlocks(false));
  }, [selectedAgentId]);

  // ── Rebuild graph when blocks or agent changes ────────────────────────────
  //
  // Depends only on blocks and selectedAgent, NOT on callbacks.
  // Callbacks are in PromptBuilderContext and don't need to be in node data.

  useEffect(() => {
    if (!selectedAgent) return;
    const { nodes: n, edges: e } = buildGraph(blocks, selectedAgent);
    setNodes(n);
    setEdges(e);
  }, [blocks, selectedAgent, setNodes, setEdges]);

  // ── Node interaction callbacks ────────────────────────────────────────────
  //
  // These are stable within an agent session (selectedAgentId dep only changes
  // on tab switch). They perform an optimistic local update then persist to API.

  const persistBlocks = useCallback(
    (updated: PromptBlockConfig[]) => {
      if (!selectedAgentId) return;
      const items: PromptBlockConfigItem[] = updated.map((b) => ({
        block_key: b.block_key,
        content: b.content,
        position: b.position,
        enabled: b.enabled,
      }));
      saveAgentBlocks(selectedAgentId, items)
        .then(setBlocks)
        .catch((e: Error) => setSaveError(e.message));
    },
    [selectedAgentId]
  );

  const handleToggle = useCallback((blockId: string) => {
    setBlocks((prev) => {
      const updated = prev.map((b) =>
        b.id === blockId ? { ...b, enabled: !b.enabled } : b
      );
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  const handleMoveUp = useCallback((blockId: string) => {
    setBlocks((prev) => {
      const sorted = [...prev].sort((a, b) => a.position - b.position);
      const idx = sorted.findIndex((b) => b.id === blockId);
      if (idx <= 0) return prev;
      const updated = sorted.map((b, i) => {
        if (i === idx - 1) return { ...b, position: sorted[idx].position };
        if (i === idx) return { ...b, position: sorted[idx - 1].position };
        return b;
      });
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  const handleMoveDown = useCallback((blockId: string) => {
    setBlocks((prev) => {
      const sorted = [...prev].sort((a, b) => a.position - b.position);
      const idx = sorted.findIndex((b) => b.id === blockId);
      if (idx < 0 || idx >= sorted.length - 1) return prev;
      const updated = sorted.map((b, i) => {
        if (i === idx) return { ...b, position: sorted[idx + 1].position };
        if (i === idx + 1) return { ...b, position: sorted[idx].position };
        return b;
      });
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  const handleEdit = useCallback((blockId: string) => {
    setEditingBlockId(blockId);
  }, []);

  // ── Stable callbacks object for context ───────────────────────────────────

  const callbacks = useMemo<PromptBuilderCallbacks>(() => ({
    onEdit: handleEdit,
    onToggle: handleToggle,
    onMoveUp: handleMoveUp,
    onMoveDown: handleMoveDown,
  }), [handleEdit, handleToggle, handleMoveUp, handleMoveDown]);

  // ── Agent update callback ─────────────────────────────────────────────────

  const handleAgentUpdated = useCallback((updated: Agent) => {
    setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────

  if (loadingAgents) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading agents…
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        No agents found for this project.
      </div>
    );
  }

  return (
    <PromptBuilderContext.Provider value={callbacks}>
      <div className="flex flex-col h-full overflow-hidden bg-[var(--surface-bg,#f8f9fa)]">
        {/* Agent selector tabs */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-200 bg-white overflow-x-auto flex-shrink-0">
          <span className="text-xs font-semibold text-gray-400 uppercase mr-2 flex-shrink-0">
            Agent
          </span>
          {agents.map((a) => (
            <button
              key={a.id}
              onClick={() => {
                setEditingBlockId(null);
                setSelectedAgentId(a.id);
              }}
              className={`
                px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex-shrink-0
                ${a.id === selectedAgentId
                  ? 'bg-violet-600 text-white shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100'
                }
              `}
            >
              {a.display_name}
              <span className="ml-1.5 text-xs opacity-60 font-normal">{a.role}</span>
            </button>
          ))}
        </div>

        {/* Canvas area */}
        <div className="flex-1 relative overflow-hidden">
          {saveError && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg px-4 py-2 shadow-md">
              {saveError}
              <button
                className="ml-3 underline"
                onClick={() => setSaveError(null)}
              >
                dismiss
              </button>
            </div>
          )}

          {loadingBlocks ? (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              Loading prompt blocks…
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.3 }}
              nodesDraggable={false}
              nodesConnectable={false}
              attributionPosition="bottom-left"
            >
              <Background color="#e5e7eb" gap={20} />
              <Controls showInteractive={false} />
            </ReactFlow>
          )}

          {/* AgentConfigPanel — floating top-right, outside React Flow */}
          {selectedAgent && (
            <div className="absolute top-4 right-4 z-20">
              <AgentConfigPanel
                agent={selectedAgent}
                onAgentUpdated={handleAgentUpdated}
              />
            </div>
          )}
        </div>

        {/* BlockEditorPanel — slide-in from right */}
        {editingBlockId && selectedAgentId && (
          <BlockEditorPanel
            agentId={selectedAgentId}
            block={editingBlock}
            allBlocks={blocks}
            onClose={() => setEditingBlockId(null)}
            onSaved={(updated) => {
              setBlocks(updated);
              setEditingBlockId(null);
            }}
          />
        )}
      </div>
    </PromptBuilderContext.Provider>
  );
}

export default PromptBuilderPage;
