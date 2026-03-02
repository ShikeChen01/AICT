/**
 * PromptBuilderPage — Context Budget Dashboard.
 *
 * Two-column layout:
 *   Left:  Context window donut chart + budget breakdown (model-aware)
 *   Right: System prompt block list + Tool Assembly section + Runtime Injections
 *
 * Meta is re-fetched when: agent changes, agent model changes, or tools are updated.
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import { Database } from 'lucide-react';

import { AgentConfigPanel } from './AgentConfigPanel';
import { AllocationEditor } from './AllocationEditor';
import { BlockEditorPanel } from './BlockEditorPanel';
import { ContextBudgetChart } from './ContextBudgetChart';
import { PromptBlockRow } from './PromptBlockRow';
import { RuntimeInjectionsGroup } from './RuntimeInjectionsGroup';
import { ThinkingStagesGroup } from './ThinkingStagesGroup';
import { ToolAssemblyPanel } from './ToolAssemblyPanel';
import { estimateTokens } from './ContextBudgetChart';

import {
  getAgents,
  listAgentBlocks,
  saveAgentBlocks,
  getPromptMeta,
} from '../../api/client';
import type { Agent, PromptBlockConfig, PromptBlockConfigItem, PromptMeta } from '../../types';

// ── Block classification ──────────────────────────────────────────────────────

const CONDITIONAL_BLOCK_KEYS = new Set([
  'loopback', 'end_solo_warning',
  'summarization', 'summarization_memory', 'summarization_history',
]);
const THINKING_BLOCK_KEYS = new Set(['thinking_stage', 'execution_stage']);

function isMainBlock(block: PromptBlockConfig): boolean {
  return !CONDITIONAL_BLOCK_KEYS.has(block.block_key) && !THINKING_BLOCK_KEYS.has(block.block_key);
}

// ── Component ─────────────────────────────────────────────────────────────────

interface PromptBuilderPageProps {
  projectId: string;
}

export function PromptBuilderPage({ projectId }: PromptBuilderPageProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<PromptBlockConfig[]>([]);
  const [meta, setMeta] = useState<PromptMeta | null>(null);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [loadingBlocks, setLoadingBlocks] = useState(false);
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingBlocks, setSavingBlocks] = useState(false);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const editingBlock = useMemo(
    () => blocks.find((b) => b.id === editingBlockId) ?? null,
    [blocks, editingBlockId]
  );

  // ── Load agents on mount ──────────────────────────────────────────────────

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

  // ── Refresh meta whenever selected agent changes ──────────────────────────
  // Passes agent_id so backend can measure exact tool + block tokens

  const refreshMeta = useCallback((agentId: string | null, agentModel?: string) => {
    if (!agentId) return;
    getPromptMeta({ agent_id: agentId, model: agentModel })
      .then(setMeta)
      .catch(console.error);
  }, []);

  useEffect(() => {
    refreshMeta(selectedAgentId, selectedAgent?.model);
  }, [selectedAgentId, selectedAgent?.model, refreshMeta]);

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

  // ── Persist helper ────────────────────────────────────────────────────────
  // Returns a promise; sets savingBlocks so reorder/toggle are disabled during save.

  const persistBlocks = useCallback(
    (updated: PromptBlockConfig[]) => {
      if (!selectedAgentId) return Promise.resolve();
      setSavingBlocks(true);
      setSaveError(null);
      const items: PromptBlockConfigItem[] = updated.map((b) => ({
        block_key: b.block_key,
        content: b.content,
        position: b.position,
        enabled: b.enabled,
      }));
      return saveAgentBlocks(selectedAgentId, items)
        .then((saved) => {
          setBlocks(saved);
          refreshMeta(selectedAgentId, selectedAgent?.model);
        })
        .catch((e: Error) => setSaveError(e.message))
        .finally(() => setSavingBlocks(false));
    },
    [selectedAgentId, selectedAgent?.model, refreshMeta]
  );

  // ── Block callbacks ───────────────────────────────────────────────────────

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
      const mainBlocks = [...prev]
        .filter(isMainBlock)
        .sort((a, b) => a.position - b.position);
      const others = prev.filter((b) => !isMainBlock(b));
      const idx = mainBlocks.findIndex((b) => b.id === blockId);
      if (idx <= 0) return prev;
      const swapped = mainBlocks.map((b, i) => {
        if (i === idx - 1) return { ...b, position: mainBlocks[idx].position };
        if (i === idx) return { ...b, position: mainBlocks[idx - 1].position };
        return b;
      });
      const updated = [...swapped, ...others];
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  const handleMoveDown = useCallback((blockId: string) => {
    setBlocks((prev) => {
      const mainBlocks = [...prev]
        .filter(isMainBlock)
        .sort((a, b) => a.position - b.position);
      const others = prev.filter((b) => !isMainBlock(b));
      const idx = mainBlocks.findIndex((b) => b.id === blockId);
      if (idx < 0 || idx >= mainBlocks.length - 1) return prev;
      const swapped = mainBlocks.map((b, i) => {
        if (i === idx) return { ...b, position: mainBlocks[idx + 1].position };
        if (i === idx + 1) return { ...b, position: mainBlocks[idx].position };
        return b;
      });
      const updated = [...swapped, ...others];
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  const handleEdit = useCallback((blockId: string) => {
    setEditingBlockId(blockId);
  }, []);

  const handleAgentUpdated = useCallback((updated: Agent) => {
    setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    refreshMeta(updated.id, updated.model);
  }, [refreshMeta]);

  const handleToolsSaved = useCallback(() => {
    refreshMeta(selectedAgentId, selectedAgent?.model);
  }, [selectedAgentId, selectedAgent?.model, refreshMeta]);

  // ── Derived block lists ───────────────────────────────────────────────────

  const mainBlocks = useMemo(
    () => blocks.filter(isMainBlock).sort((a, b) => a.position - b.position),
    [blocks]
  );

  const totalSystemTokens = useMemo(
    () => mainBlocks.filter((b) => b.enabled).reduce((sum, b) => sum + estimateTokens(b.content), 0),
    [mainBlocks]
  );

  // ── Loading / empty states ────────────────────────────────────────────────

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
    <div className="flex flex-col h-full overflow-hidden bg-[#f8f9fa]">
      {/* ── Top bar: agent tabs ── */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-white flex-shrink-0 overflow-x-auto">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide mr-1 flex-shrink-0">
          Agent
        </span>
        {agents.map((a) => (
          <button
            key={a.id}
            type="button"
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

        <div className="flex items-center gap-1 ml-auto flex-shrink-0 text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-1">
          <Database className="w-3 h-3" />
          <span>DB is source of truth</span>
        </div>
      </div>

      {/* ── Main content: two-column layout ── */}
      <div className="flex flex-1 min-h-0 gap-0">

        {/* Left column: context budget */}
        <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
          <div className="p-4 space-y-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Context Budget
            </h3>

            {meta ? (
              <ContextBudgetChart meta={meta} />
            ) : (
              <div className="text-xs text-gray-400">Loading budget…</div>
            )}

            {/* Dynamic pool — editable allocation panel */}
            {meta && selectedAgentId && (
              <div className="pt-3 border-t border-gray-100">
                <AllocationEditor
                  agentId={selectedAgentId}
                  meta={meta}
                  model={selectedAgent?.model}
                  onSaved={() => refreshMeta(selectedAgentId, selectedAgent?.model)}
                />
              </div>
            )}

            {/* Agent config */}
            {selectedAgent && (
              <div className="pt-3 border-t border-gray-100">
                <AgentConfigPanel
                  agent={selectedAgent}
                  onAgentUpdated={handleAgentUpdated}
                />
              </div>
            )}
          </div>
        </div>

        {/* Right column: block list + tool assembly */}
        <div className="flex-1 min-w-0 overflow-y-auto">
          <div className="p-4 space-y-6 max-w-2xl">
            {/* System Prompt Blocks section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  System Prompt Blocks
                </h3>
                <span className="text-xs text-gray-400 font-mono" title="Assembled tokens / measured allocation">
                  ~{(totalSystemTokens / 1000).toFixed(1)}k
                  {meta ? ` / ${(meta.system_prompt_tokens / 1000).toFixed(1)}k` : ''} tokens
                </span>
              </div>

              {saveError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg px-3 py-2 flex items-center justify-between">
                  {saveError}
                  <button
                    type="button"
                    className="underline ml-2"
                    onClick={() => setSaveError(null)}
                  >
                    dismiss
                  </button>
                </div>
              )}

              {loadingBlocks ? (
                <div className="text-sm text-gray-400 py-6 text-center">
                  Loading prompt blocks…
                </div>
              ) : mainBlocks.length === 0 ? (
                <div className="text-sm text-gray-400 py-6 text-center">
                  No blocks found. Try refreshing.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {mainBlocks.map((block, idx) => (
                    <PromptBlockRow
                      key={block.id}
                      block={block}
                      meta={meta?.block_registry[block.block_key]}
                      totalSystemTokens={totalSystemTokens}
                      isFirst={idx === 0}
                      isLast={idx === mainBlocks.length - 1}
                      mutationsDisabled={savingBlocks}
                      onEdit={() => handleEdit(block.id)}
                      onToggle={() => handleToggle(block.id)}
                      onMoveUp={() => handleMoveUp(block.id)}
                      onMoveDown={() => handleMoveDown(block.id)}
                    />
                  ))}
                </div>
              )}

              {!loadingBlocks && (
                <RuntimeInjectionsGroup
                  blocks={blocks}
                  blockRegistry={meta?.block_registry ?? {}}
                  mutationsDisabled={savingBlocks}
                  onEdit={handleEdit}
                  onToggle={handleToggle}
                />
              )}

              {!loadingBlocks && selectedAgent && (
                <ThinkingStagesGroup
                  blocks={blocks}
                  thinkingEnabled={selectedAgent.thinking_enabled}
                  mutationsDisabled={savingBlocks}
                  onEdit={handleEdit}
                  onToggle={handleToggle}
                />
              )}
            </div>

            {/* Tool Assembly section */}
            {selectedAgent && selectedAgentId && (
              <div className="space-y-3">
                <div className="border-t border-gray-200 pt-4">
                  <ToolAssemblyPanel
                    agentId={selectedAgentId}
                    agent={selectedAgent}
                    meta={meta}
                    onToolsSaved={handleToolsSaved}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Block editor slide-in */}
      {editingBlockId && selectedAgentId && (
        <BlockEditorPanel
          agentId={selectedAgentId}
          block={editingBlock}
          onClose={() => setEditingBlockId(null)}
          onSaved={(updated) => {
            setBlocks(updated);
            setEditingBlockId(null);
            refreshMeta(selectedAgentId, selectedAgent?.model);
          }}
        />
      )}
    </div>
  );
}

export default PromptBuilderPage;
