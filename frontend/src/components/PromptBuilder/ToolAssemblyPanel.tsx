/**
 * ToolAssemblyPanel — collapsible section for per-agent tool customization.
 *
 * Shows all tools for the agent with:
 *   - Enable/disable toggle
 *   - Description preview + token estimate
 *   - Inline editor for description and detailed_description
 *   - Token budget bar (% of 5% cap)
 *   - Reset to default button
 *
 * DB is the source of truth for tool definitions.
 * Structural fields (tool_name, input_schema, allowed_roles) are read-only.
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import { ChevronRight, ChevronDown, Pencil, Eye, EyeOff, RotateCcw, Wrench, Save, X, AlertTriangle } from 'lucide-react';
import type { Agent, ToolConfig, ToolConfigUpdateItem, PromptMeta } from '../../types';
import {
  listAgentTools,
  saveAgentTools,
  resetAgentTool,
} from '../../api/client';

const _CHARS_PER_TOKEN = 4;

function estimateToolTokens(tool: { tool_name: string; description: string; input_schema?: unknown }): number {
  const payload = JSON.stringify({
    name: tool.tool_name,
    description: tool.description,
    input_schema: tool.input_schema ?? {},
  });
  return Math.max(1, Math.floor(payload.length / _CHARS_PER_TOKEN));
}

interface ToolAssemblyPanelProps {
  agentId: string;
  agent: Agent;
  meta: PromptMeta | null;
  onToolsSaved?: () => void;
}

interface EditState {
  description: string;
  detailed_description: string;
}

export function ToolAssemblyPanel({
  agentId,
  agent: _agent,
  meta,
  onToolsSaved,
}: ToolAssemblyPanelProps) {
  const [open, setOpen] = useState(false);
  const [tools, setTools] = useState<ToolConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState>({ description: '', detailed_description: '' });
  const [dirty, setDirty] = useState(false);

  // Max tool schema tokens = 5% of context window
  const maxTokens = meta ? Math.floor(meta.context_window_tokens * 0.05) : 10_000;

  // Load tools when panel opens
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    listAgentTools(agentId)
      .then(setTools)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [open, agentId]);

  const totalTokens = useMemo(
    () => tools.filter(t => t.enabled).reduce((sum, t) => sum + (t.estimated_tokens || estimateToolTokens(t)), 0),
    [tools]
  );

  const budgetPct = maxTokens > 0 ? Math.min(1, totalTokens / maxTokens) : 0;
  const budgetOverLimit = totalTokens > maxTokens;

  const editingTool = tools.find(t => t.id === editingToolId) ?? null;

  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

  // ── Toggle enabled ──────────────────────────────────────────────────────

  const handleToggle = useCallback(async (toolId: string) => {
    const updated = tools.map(t =>
      t.id === toolId ? { ...t, enabled: !t.enabled } : t
    );
    setTools(updated);
    setDirty(true);
  }, [tools]);

  // ── Open editor ─────────────────────────────────────────────────────────

  const handleEdit = useCallback((tool: ToolConfig) => {
    setEditingToolId(tool.id);
    setEditState({
      description: tool.description,
      detailed_description: tool.detailed_description ?? '',
    });
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingToolId(null);
  }, []);

  const handleSaveEdit = useCallback(() => {
    if (!editingToolId) return;
    setTools(prev => prev.map(t =>
      t.id === editingToolId
        ? { ...t, description: editState.description, detailed_description: editState.detailed_description }
        : t
    ));
    setEditingToolId(null);
    setDirty(true);
  }, [editingToolId, editState]);

  // ── Reset single tool ───────────────────────────────────────────────────

  const handleReset = useCallback(async (tool: ToolConfig) => {
    try {
      const resetTool = await resetAgentTool(agentId, tool.id);
      setTools(prev => prev.map(t => t.id === tool.id ? resetTool : t));
      setDirty(true);
    } catch (e) {
      console.error('Reset failed', e);
    }
  }, [agentId]);

  // ── Save all changes ────────────────────────────────────────────────────

  const handleSaveAll = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    const items: ToolConfigUpdateItem[] = tools.map((t, i) => ({
      tool_name: t.tool_name,
      description: t.description,
      detailed_description: t.detailed_description ?? undefined,
      enabled: t.enabled,
      position: i,
    }));
    try {
      const saved = await saveAgentTools(agentId, items);
      setTools(saved);
      setDirty(false);
      onToolsSaved?.();
    } catch (e: unknown) {
      const err = e as { detail?: { message?: string } | string };
      if (err?.detail && typeof err.detail === 'object' && err.detail.message) {
        setSaveError(err.detail.message);
      } else if (typeof err?.detail === 'string') {
        setSaveError(err.detail);
      } else {
        setSaveError('Failed to save tool configs.');
      }
    } finally {
      setSaving(false);
    }
  }, [agentId, tools, onToolsSaved]);

  return (
    <div className="border border-[var(--color-primary)]/20 rounded-lg overflow-hidden bg-[var(--color-primary)]/5">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[var(--color-primary)]/10 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        {open
          ? <ChevronDown className="w-4 h-4 text-[var(--color-primary)] flex-shrink-0" />
          : <ChevronRight className="w-4 h-4 text-[var(--color-primary)] flex-shrink-0" />
        }
        <Wrench className="w-3.5 h-3.5 text-[var(--color-primary)] flex-shrink-0" />
        <span className="text-sm font-semibold text-[var(--color-primary)]">Tool Assembly</span>
        {tools.length > 0 && (
          <span className="text-xs text-[var(--color-primary)] ml-1">
            ({tools.filter(t => t.enabled).length}/{tools.length} enabled)
          </span>
        )}
        {/* Token budget summary in header */}
        {tools.length > 0 && (
          <span className={`ml-2 text-xs font-mono ${budgetOverLimit ? 'text-[var(--color-danger)]' : 'text-[var(--color-primary)]'}`}>
            {fmt(totalTokens)} / {fmt(maxTokens)} tok
          </span>
        )}
        {dirty && (
          <span className="ml-2 text-xs text-[var(--color-warning)] font-medium">unsaved</span>
        )}
        <span className="ml-auto text-xs text-[var(--color-primary)]">Edit tool descriptions &amp; visibility</span>
      </button>

      {/* Body */}
      {open && (
        <div className="border-t border-[var(--color-primary)]/20">
          {/* Budget bar */}
          <div className="px-3 py-2 bg-[var(--surface-card)] border-b border-[var(--color-primary)]/10">
            <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
              <span>Tool Schema Budget (5% of {fmt(meta?.context_window_tokens ?? 200_000)} tok)</span>
              <span className={`font-mono font-medium ${budgetOverLimit ? 'text-[var(--color-danger)]' : 'text-[var(--text-primary)]'}`}>
                {fmt(totalTokens)} / {fmt(maxTokens)}
              </span>
            </div>
            <div className="h-1.5 bg-[var(--surface-muted)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(100, budgetPct * 100)}%`,
                  backgroundColor: budgetOverLimit ? 'var(--color-danger)' : 'var(--color-primary)',
                }}
              />
            </div>
            {budgetOverLimit && (
              <div className="flex items-center gap-1.5 mt-1.5 text-xs text-[var(--color-danger)]">
                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                <span>Tool descriptions exceed budget. Shorten descriptions or disable tools before saving.</span>
              </div>
            )}
          </div>

          {/* Save error */}
          {saveError && (
            <div className="mx-3 mt-2 bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-xs rounded-lg px-3 py-2 flex items-center justify-between">
              {saveError}
              <button type="button" className="underline ml-2" onClick={() => setSaveError(null)}>
                dismiss
              </button>
            </div>
          )}

          {/* Inline editor */}
          {editingTool && (
            <div className="mx-3 my-2 border border-[var(--color-primary)]/20 rounded-lg bg-[var(--surface-card)] p-3 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-[var(--text-primary)]">
                  Editing: <code className="bg-[var(--surface-muted)] px-1 rounded text-[var(--color-primary)]">{editingTool.tool_name}</code>
                </span>
                <button type="button" onClick={handleCancelEdit} className="p-1 hover:bg-[var(--surface-hover)] rounded text-[var(--text-muted)]">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-0.5">
                  Short description (shown to LLM in tool list)
                </label>
                <textarea
                  className="w-full text-xs border border-[var(--border-color)] rounded p-1.5 resize-none focus:ring-1 focus:ring-[var(--color-primary)] focus:outline-none"
                  rows={2}
                  value={editState.description}
                  onChange={e => setEditState(s => ({ ...s, description: e.target.value }))}
                />
                <div className="text-right text-xs text-[var(--text-muted)] mt-0.5">
                  ~{Math.max(1, Math.floor(editState.description.length / _CHARS_PER_TOKEN))} tokens
                </div>
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-0.5">
                  Detailed description (shown by describe_tool)
                </label>
                <textarea
                  className="w-full text-xs border border-[var(--border-color)] rounded p-1.5 resize-none focus:ring-1 focus:ring-[var(--color-primary)] focus:outline-none"
                  rows={4}
                  value={editState.detailed_description}
                  onChange={e => setEditState(s => ({ ...s, detailed_description: e.target.value }))}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={handleCancelEdit}
                  className="text-xs px-2.5 py-1 rounded border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  className="text-xs px-2.5 py-1 rounded bg-[var(--color-primary)] text-white hover:opacity-90"
                >
                  Apply
                </button>
              </div>
            </div>
          )}

          {/* Tool rows */}
          {loading ? (
            <div className="text-sm text-[var(--text-muted)] py-6 text-center">Loading tools…</div>
          ) : (
            <div className="divide-y divide-[var(--color-primary)]/10 max-h-96 overflow-y-auto">
              {tools.map((tool) => {
                const tok = tool.estimated_tokens || estimateToolTokens(tool);
                const pct = maxTokens > 0 ? tok / maxTokens : 0;
                return (
                  <div
                    key={tool.id}
                    className={`flex items-start gap-2.5 px-3 py-2 group ${tool.enabled ? '' : 'opacity-50'}`}
                  >
                    {/* Toggle */}
                    <button
                      type="button"
                      className="mt-0.5 flex-shrink-0 text-[var(--color-primary)] hover:opacity-80 transition-colors"
                      title={tool.enabled ? 'Disable' : 'Enable'}
                      onClick={() => handleToggle(tool.id)}
                    >
                      {tool.enabled
                        ? <Eye className="w-3.5 h-3.5" />
                        : <EyeOff className="w-3.5 h-3.5" />
                      }
                    </button>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono font-medium text-[var(--text-primary)] truncate">
                          {tool.tool_name}
                        </code>
                        <span className="text-xs font-mono text-[var(--color-primary)] tabular-nums flex-shrink-0">
                          ~{fmt(tok)} tok
                        </span>
                        {/* Mini token bar */}
                        <div className="flex-1 max-w-24 h-1 bg-[var(--surface-muted)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-[var(--color-primary)]"
                            style={{ width: `${Math.min(100, pct * 100)}%` }}
                          />
                        </div>
                      </div>
                      <p className="text-xs text-[var(--text-muted)] truncate mt-0.5">{tool.description}</p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-[var(--color-primary)]/10 text-[var(--color-primary)] transition-colors"
                        title="Edit description"
                        onClick={() => handleEdit(tool)}
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--text-muted)] transition-colors"
                        title="Reset to default"
                        onClick={() => handleReset(tool)}
                      >
                        <RotateCcw className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Save all button */}
          {dirty && (
            <div className="px-3 py-2.5 border-t border-[var(--color-primary)]/10 bg-[var(--surface-card)] flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">Unsaved changes</span>
              <button
                type="button"
                disabled={saving || budgetOverLimit}
                onClick={handleSaveAll}
                className={`
                  flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors
                  ${budgetOverLimit
                    ? 'bg-[var(--surface-muted)] text-[var(--text-muted)] cursor-not-allowed'
                    : 'bg-[var(--color-primary)] text-white hover:opacity-90 disabled:opacity-50'
                  }
                `}
                title={budgetOverLimit ? 'Tool descriptions exceed budget' : undefined}
              >
                <Save className="w-3 h-3" />
                {saving ? 'Saving…' : 'Save Tools'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
