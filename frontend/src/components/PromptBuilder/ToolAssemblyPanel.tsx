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
    <div className="border border-blue-200 rounded-lg overflow-hidden bg-blue-50/30">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-blue-50 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        {open
          ? <ChevronDown className="w-4 h-4 text-blue-600 flex-shrink-0" />
          : <ChevronRight className="w-4 h-4 text-blue-600 flex-shrink-0" />
        }
        <Wrench className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
        <span className="text-sm font-semibold text-blue-800">Tool Assembly</span>
        {tools.length > 0 && (
          <span className="text-xs text-blue-600 ml-1">
            ({tools.filter(t => t.enabled).length}/{tools.length} enabled)
          </span>
        )}
        {/* Token budget summary in header */}
        {tools.length > 0 && (
          <span className={`ml-2 text-xs font-mono ${budgetOverLimit ? 'text-red-600' : 'text-blue-500'}`}>
            {fmt(totalTokens)} / {fmt(maxTokens)} tok
          </span>
        )}
        {dirty && (
          <span className="ml-2 text-xs text-orange-600 font-medium">unsaved</span>
        )}
        <span className="ml-auto text-xs text-blue-500">Edit tool descriptions &amp; visibility</span>
      </button>

      {/* Body */}
      {open && (
        <div className="border-t border-blue-200">
          {/* Budget bar */}
          <div className="px-3 py-2 bg-white border-b border-blue-100">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Tool Schema Budget (5% of {fmt(meta?.context_window_tokens ?? 200_000)} tok)</span>
              <span className={`font-mono font-medium ${budgetOverLimit ? 'text-red-600' : 'text-gray-700'}`}>
                {fmt(totalTokens)} / {fmt(maxTokens)}
              </span>
            </div>
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(100, budgetPct * 100)}%`,
                  backgroundColor: budgetOverLimit ? '#ef4444' : '#3b82f6',
                }}
              />
            </div>
            {budgetOverLimit && (
              <div className="flex items-center gap-1.5 mt-1.5 text-xs text-red-600">
                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                <span>Tool descriptions exceed budget. Shorten descriptions or disable tools before saving.</span>
              </div>
            )}
          </div>

          {/* Save error */}
          {saveError && (
            <div className="mx-3 mt-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg px-3 py-2 flex items-center justify-between">
              {saveError}
              <button type="button" className="underline ml-2" onClick={() => setSaveError(null)}>
                dismiss
              </button>
            </div>
          )}

          {/* Inline editor */}
          {editingTool && (
            <div className="mx-3 my-2 border border-blue-200 rounded-lg bg-white p-3 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-gray-700">
                  Editing: <code className="bg-gray-100 px-1 rounded text-blue-700">{editingTool.tool_name}</code>
                </span>
                <button type="button" onClick={handleCancelEdit} className="p-1 hover:bg-gray-100 rounded text-gray-400">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-0.5">
                  Short description (shown to LLM in tool list)
                </label>
                <textarea
                  className="w-full text-xs border border-gray-200 rounded p-1.5 resize-none focus:ring-1 focus:ring-blue-300 focus:outline-none"
                  rows={2}
                  value={editState.description}
                  onChange={e => setEditState(s => ({ ...s, description: e.target.value }))}
                />
                <div className="text-right text-xs text-gray-400 mt-0.5">
                  ~{Math.max(1, Math.floor(editState.description.length / _CHARS_PER_TOKEN))} tokens
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-0.5">
                  Detailed description (shown by describe_tool)
                </label>
                <textarea
                  className="w-full text-xs border border-gray-200 rounded p-1.5 resize-none focus:ring-1 focus:ring-blue-300 focus:outline-none"
                  rows={4}
                  value={editState.detailed_description}
                  onChange={e => setEditState(s => ({ ...s, detailed_description: e.target.value }))}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={handleCancelEdit}
                  className="text-xs px-2.5 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  className="text-xs px-2.5 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                >
                  Apply
                </button>
              </div>
            </div>
          )}

          {/* Tool rows */}
          {loading ? (
            <div className="text-sm text-gray-400 py-6 text-center">Loading tools…</div>
          ) : (
            <div className="divide-y divide-blue-100 max-h-96 overflow-y-auto">
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
                      className="mt-0.5 flex-shrink-0 text-blue-500 hover:text-blue-700 transition-colors"
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
                        <code className="text-xs font-mono font-medium text-gray-800 truncate">
                          {tool.tool_name}
                        </code>
                        <span className="text-xs font-mono text-blue-500 tabular-nums flex-shrink-0">
                          ~{fmt(tok)} tok
                        </span>
                        {/* Mini token bar */}
                        <div className="flex-1 max-w-24 h-1 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-blue-400"
                            style={{ width: `${Math.min(100, pct * 100)}%` }}
                          />
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 truncate mt-0.5">{tool.description}</p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-blue-100 text-blue-500 transition-colors"
                        title="Edit description"
                        onClick={() => handleEdit(tool)}
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 transition-colors"
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
            <div className="px-3 py-2.5 border-t border-blue-100 bg-white flex items-center justify-between">
              <span className="text-xs text-gray-500">Unsaved changes</span>
              <button
                type="button"
                disabled={saving || budgetOverLimit}
                onClick={handleSaveAll}
                className={`
                  flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors
                  ${budgetOverLimit
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50'
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
