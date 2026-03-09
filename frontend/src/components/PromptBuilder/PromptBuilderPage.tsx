/**
 * PromptBuilderPage — Agent Builder: prompt blocks, tools, context budget.
 *
 * Two-column layout with draggable divider:
 *   Left:  Context window donut chart + budget breakdown (model-aware) + agent config
 *   Right: System prompt block list + custom blocks + Tool Assembly + Runtime Injections
 *
 * Meta is re-fetched when: agent changes, agent model changes, or tools are updated.
 */

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Database, Plus, X, Settings2 } from 'lucide-react';

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

function isCustomBlock(block: PromptBlockConfig): boolean {
  return block.block_key.startsWith('custom_');
}

// ── Draggable divider — uses % of container, clamped to usable range ──────────

const MIN_LEFT_PCT = 18;   // minimum ~18% of container
const MAX_LEFT_PCT = 38;   // maximum ~38% of container
const DEFAULT_LEFT_PCT = 25; // default ~25%

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

  // Draggable left column (percentage-based)
  const [leftPct, setLeftPct] = useState(DEFAULT_LEFT_PCT);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Agent config popover (now in the top bar, not the sidebar)
  const [showAgentConfig, setShowAgentConfig] = useState(false);
  const configBtnRef = useRef<HTMLButtonElement>(null);

  // Add custom block form
  const [showAddBlock, setShowAddBlock] = useState(false);
  const [newBlockName, setNewBlockName] = useState('');
  const [newBlockContent, setNewBlockContent] = useState('');

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const editingBlock = useMemo(
    () => blocks.find((b) => b.id === editingBlockId) ?? null,
    [blocks, editingBlockId]
  );

  // ── Draggable resize logic ─────────────────────────────────────────────────

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect || rect.width === 0) return;
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftPct(Math.min(MAX_LEFT_PCT, Math.max(MIN_LEFT_PCT, pct)));
    };
    const onUp = () => setIsDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isDragging]);

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
  //
  // IMPORTANT: persistBlocks must be called OUTSIDE the setBlocks updater.
  // React may invoke updater functions multiple times (strict mode, concurrent
  // rendering), and calling an async side-effect inside an updater causes
  // duplicate API calls that race against each other, triggering the backend's
  // unique constraint on (agent_id, block_key).

  const handleToggle = useCallback((blockId: string) => {
    let result: PromptBlockConfig[] | null = null;
    setBlocks((prev) => {
      result = prev.map((b) =>
        b.id === blockId ? { ...b, enabled: !b.enabled } : b
      );
      return result;
    });
    queueMicrotask(() => {
      if (result) persistBlocks(result);
    });
  }, [persistBlocks]);

  const handleMoveUp = useCallback((blockId: string) => {
    let result: PromptBlockConfig[] | null = null;
    setBlocks((prev) => {
      const sorted = [...prev]
        .filter(isMainBlock)
        .sort((a, b) => a.position - b.position);
      const others = prev.filter((b) => !isMainBlock(b));
      const idx = sorted.findIndex((b) => b.id === blockId);
      if (idx <= 0) return prev;
      const swapped = sorted.map((b, i) => {
        if (i === idx - 1) return { ...b, position: sorted[idx].position };
        if (i === idx) return { ...b, position: sorted[idx - 1].position };
        return b;
      });
      result = [...swapped, ...others];
      return result;
    });
    // Persist outside the updater — use a microtask to ensure state has settled
    queueMicrotask(() => {
      if (result) persistBlocks(result);
    });
  }, [persistBlocks]);

  const handleMoveDown = useCallback((blockId: string) => {
    let result: PromptBlockConfig[] | null = null;
    setBlocks((prev) => {
      const sorted = [...prev]
        .filter(isMainBlock)
        .sort((a, b) => a.position - b.position);
      const others = prev.filter((b) => !isMainBlock(b));
      const idx = sorted.findIndex((b) => b.id === blockId);
      if (idx < 0 || idx >= sorted.length - 1) return prev;
      const swapped = sorted.map((b, i) => {
        if (i === idx) return { ...b, position: sorted[idx + 1].position };
        if (i === idx + 1) return { ...b, position: sorted[idx].position };
        return b;
      });
      result = [...swapped, ...others];
      return result;
    });
    queueMicrotask(() => {
      if (result) persistBlocks(result);
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

  // ── Add custom block ───────────────────────────────────────────────────────

  const handleAddCustomBlock = useCallback(() => {
    if (!newBlockName.trim() || !selectedAgentId) return;
    const blockKey = `custom_${newBlockName.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')}`;
    const maxPos = blocks.reduce((max, b) => Math.max(max, b.position), 0);
    const newBlock: PromptBlockConfig = {
      id: `temp_${Date.now()}`,
      template_id: null,
      agent_id: selectedAgentId,
      block_key: blockKey,
      content: newBlockContent.trim() || `# ${newBlockName.trim()}\n\nYour custom instructions here.`,
      position: maxPos + 1,
      enabled: true,
    };
    const updated = [...blocks, newBlock];
    setBlocks(updated);
    persistBlocks(updated);
    setNewBlockName('');
    setNewBlockContent('');
    setShowAddBlock(false);
  }, [newBlockName, newBlockContent, blocks, selectedAgentId, persistBlocks]);

  // ── Delete custom block ────────────────────────────────────────────────────

  const handleDeleteBlock = useCallback((blockId: string) => {
    setBlocks((prev) => {
      const updated = prev.filter((b) => b.id !== blockId);
      persistBlocks(updated);
      return updated;
    });
  }, [persistBlocks]);

  // ── Derived block lists ───────────────────────────────────────────────────

  const mainBlocks = useMemo(
    () => blocks.filter((b) => isMainBlock(b) && !isCustomBlock(b)).sort((a, b) => a.position - b.position),
    [blocks]
  );

  const customBlocks = useMemo(
    () => blocks.filter(isCustomBlock).sort((a, b) => a.position - b.position),
    [blocks]
  );

  const totalSystemTokens = useMemo(
    () => [...mainBlocks, ...customBlocks].filter((b) => b.enabled).reduce((sum, b) => sum + estimateTokens(b.content), 0),
    [mainBlocks, customBlocks]
  );

  // ── Loading / empty states ────────────────────────────────────────────────

  if (loadingAgents) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)] text-sm">
        Loading agents…
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)] text-sm">
        No agents found for this project.
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-hidden bg-[var(--app-bg)]">
      {/* ── Top bar: agent tabs + config button — compact, pinned ── */}
      <div className="flex items-center gap-1.5 px-3 py-1 border-b border-[var(--border-color)] bg-[var(--surface-card)] flex-shrink-0 overflow-x-auto" role="tablist" aria-label="Agent selector">
        <span className="text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider mr-0.5 flex-shrink-0" aria-hidden="true">
          Agent
        </span>
        {agents.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={a.id === selectedAgentId}
            aria-controls="prompt-builder-content"
            onClick={() => {
              setEditingBlockId(null);
              setShowAgentConfig(false);
              setSelectedAgentId(a.id);
            }}
            className={`
              px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex-shrink-0
              ${a.id === selectedAgentId
                ? 'bg-[var(--color-accent)] text-white shadow-sm'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
              }
            `}
          >
            {a.display_name}
            <span className="ml-1 text-[10px] opacity-60 font-normal">{a.role}</span>
          </button>
        ))}

        {/* Agent config button — opens popover */}
        {selectedAgent && (
          <div className="flex-shrink-0 ml-1">
            <button
              ref={configBtnRef}
              type="button"
              onClick={() => setShowAgentConfig((v) => !v)}
              className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                showAgentConfig
                  ? 'bg-[var(--color-accent)]/15 text-[var(--color-accent)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
              }`}
              aria-expanded={showAgentConfig}
              aria-haspopup="dialog"
              aria-label={`Configure ${selectedAgent.display_name}`}
            >
              <Settings2 className="w-3.5 h-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Config</span>
            </button>
          </div>
        )}

        <div className="flex items-center gap-1 ml-auto flex-shrink-0 text-[10px] text-[var(--color-success)] bg-[var(--color-success-light)] border border-[var(--color-success)]/20 rounded-full px-2 py-0.5" role="status">
          <Database className="w-2.5 h-2.5" aria-hidden="true" />
          <span>DB synced</span>
        </div>
      </div>

      {/* ── Scrollable content area — whole page scrolls as one unit ── */}
      <div ref={containerRef} id="prompt-builder-content" role="tabpanel" className="flex-1 min-h-0 overflow-y-auto">
        <div className="flex min-h-full">

          {/* Left column: context budget — sticky sidebar */}
          <div
            className="flex-shrink-0 border-r border-[var(--border-color)] bg-[var(--surface-card)] self-start sticky top-0"
            style={{ width: `${leftPct}%` }}
          >
            <div className="p-3 space-y-3 pb-12 max-h-[calc(100vh-6rem)] overflow-y-auto">
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Context Budget
            </h3>

            {meta ? (
              <ContextBudgetChart meta={meta} />
            ) : (
              <div className="text-xs text-[var(--text-muted)]">Loading budget…</div>
            )}

            {/* Dynamic pool — editable allocation panel */}
            {meta && selectedAgentId && (
              <div className="pt-3 border-t border-[var(--border-color-subtle)]">
                <AllocationEditor
                  agentId={selectedAgentId}
                  meta={meta}
                  model={selectedAgent?.model}
                  onSaved={() => refreshMeta(selectedAgentId, selectedAgent?.model)}
                />
              </div>
            )}

          </div>
        </div>

          {/* Draggable divider — sticky so it stays visible while scrolling */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize left panel"
            onMouseDown={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            className="w-1.5 flex-shrink-0 cursor-col-resize bg-transparent hover:bg-[var(--border-color)] active:bg-[var(--color-primary)]/40 transition-colors sticky top-0 self-start"
            style={{ height: 'calc(100vh - 6rem)' }}
          />

          {/* Right column: block list + tool assembly — flows naturally, page scrolls */}
          <div className="flex-1 min-w-0">
            <div className="p-4 space-y-6 max-w-2xl pb-16">
            {/* System Prompt Blocks section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                  System Prompt Blocks
                </h3>
                <span className="text-xs text-[var(--text-muted)] font-mono" title="Assembled tokens / measured allocation">
                  ~{(totalSystemTokens / 1000).toFixed(1)}k
                  {meta ? ` / ${(meta.system_prompt_tokens / 1000).toFixed(1)}k` : ''} tokens
                </span>
              </div>

              {saveError && (
                <div className="bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-xs rounded-lg px-3 py-2 flex items-center justify-between">
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
                <div className="text-sm text-[var(--text-muted)] py-6 text-center">
                  Loading prompt blocks…
                </div>
              ) : mainBlocks.length === 0 ? (
                <div className="text-sm text-[var(--text-muted)] py-6 text-center">
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

              {/* Custom Blocks section */}
              {customBlocks.length > 0 && (
                <div className="space-y-1.5 pt-2">
                  <h4 className="text-xs font-semibold text-[var(--color-accent)] uppercase tracking-wide flex items-center gap-1">
                    Custom Blocks
                    <span className="text-[var(--text-muted)] font-normal">({customBlocks.length})</span>
                  </h4>
                  {customBlocks.map((block, idx) => (
                    <div key={block.id} className="relative group/custom">
                      <PromptBlockRow
                        block={block}
                        meta={undefined}
                        totalSystemTokens={totalSystemTokens}
                        isFirst={idx === 0}
                        isLast={idx === customBlocks.length - 1}
                        mutationsDisabled={savingBlocks}
                        onEdit={() => handleEdit(block.id)}
                        onToggle={() => handleToggle(block.id)}
                        onMoveUp={() => handleMoveUp(block.id)}
                        onMoveDown={() => handleMoveDown(block.id)}
                      />
                      {/* Delete button for custom blocks */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete custom block "${block.block_key.replace('custom_', '')}"?`)) {
                            handleDeleteBlock(block.id);
                          }
                        }}
                        className="absolute -right-1 -top-1 hidden group-hover/custom:flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-danger)] text-white shadow-sm text-xs"
                        title="Delete custom block"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add Custom Block */}
              {!showAddBlock ? (
                <button
                  type="button"
                  onClick={() => setShowAddBlock(true)}
                  disabled={savingBlocks}
                  className="flex items-center gap-1.5 text-xs text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] font-medium transition-colors disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Custom Block
                </button>
              ) : (
                <div className="border border-[var(--color-primary)]/20 rounded-lg bg-[var(--surface-card)] p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-[var(--text-primary)]">New Custom Block</h4>
                    <button
                      type="button"
                      onClick={() => { setShowAddBlock(false); setNewBlockName(''); setNewBlockContent(''); }}
                      className="p-0.5 rounded hover:bg-[var(--surface-hover)] text-[var(--text-muted)]"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div>
                    <label className="block text-xs text-[var(--text-muted)] mb-0.5">Block name</label>
                    <input
                      type="text"
                      value={newBlockName}
                      onChange={(e) => setNewBlockName(e.target.value)}
                      placeholder="e.g. coding_style, safety_rules"
                      className="w-full text-sm border border-[var(--border-color)] bg-[var(--surface-muted)] rounded-lg px-2.5 py-1.5 text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] placeholder:text-[var(--text-faint)]"
                    />
                    <p className="text-[10px] text-[var(--text-faint)] mt-0.5">
                      Will be saved as: custom_{newBlockName.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') || '...'}
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs text-[var(--text-muted)] mb-0.5">Initial content (optional)</label>
                    <textarea
                      value={newBlockContent}
                      onChange={(e) => setNewBlockContent(e.target.value)}
                      rows={3}
                      placeholder="Markdown content for this block…"
                      className="w-full text-xs font-mono border border-[var(--border-color)] bg-[var(--surface-muted)] rounded-lg p-2 text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] placeholder:text-[var(--text-faint)] resize-none"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => { setShowAddBlock(false); setNewBlockName(''); setNewBlockContent(''); }}
                      className="text-xs px-2.5 py-1 rounded border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleAddCustomBlock}
                      disabled={!newBlockName.trim() || savingBlocks}
                      className="text-xs px-3 py-1 rounded bg-[var(--color-primary)] text-white hover:opacity-90 disabled:opacity-40 font-medium"
                    >
                      Add Block
                    </button>
                  </div>
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
                <div className="border-t border-[var(--border-color)] pt-4">
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

      {/* Agent config popover — rendered at root level to escape overflow clipping */}
      {showAgentConfig && selectedAgent && (
        <>
          <div
            className="fixed inset-0 z-30"
            onClick={() => setShowAgentConfig(false)}
            aria-hidden="true"
          />
          {/* eslint-disable react-hooks/refs */}
          <div
            className="fixed z-40"
            style={{
              top: configBtnRef.current
                ? configBtnRef.current.getBoundingClientRect().bottom + 4
                : 60,
              left: configBtnRef.current
                ? configBtnRef.current.getBoundingClientRect().left
                : 16,
            }}
            role="dialog"
            aria-label="Agent configuration"
          >
            <AgentConfigPanel
              agent={selectedAgent}
              onAgentUpdated={handleAgentUpdated}
            />
          </div>
          {/* eslint-enable react-hooks/refs */}
        </>
      )}
    </div>
  );
}

export default PromptBuilderPage;
