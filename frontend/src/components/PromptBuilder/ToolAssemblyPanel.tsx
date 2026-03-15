/**
 * ToolAssemblyPanel — unified tool builder for per-agent tool customization.
 *
 * Shows all tools (native + MCP) in a single view with:
 *   - Source badge (native / mcp server name)
 *   - Enable/disable toggle
 *   - Description preview + token estimate
 *   - Inline editor for description and detailed_description
 *   - Token budget bar (% of 5% cap)
 *   - Reset to default button (native tools only)
 *   - MCP server management section (add, sync, remove servers)
 *
 * DB is the source of truth for tool definitions.
 * Structural fields (tool_name, input_schema, allowed_roles) are read-only.
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  ChevronRight, ChevronDown, Pencil, Eye, EyeOff, RotateCcw, Wrench,
  Save, X, AlertTriangle, Plus, RefreshCw, Trash2, Plug, Unplug, Server,
} from 'lucide-react';
import type { Agent, ToolConfig, ToolConfigUpdateItem, PromptMeta, McpServer } from '../../types';
import {
  listAgentTools,
  saveAgentTools,
  resetAgentTool,
  listMcpServers,
  createMcpServer,
  deleteMcpServer,
  syncMcpServer,
  updateMcpServer,
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

type ViewTab = 'tools' | 'servers';

export function ToolAssemblyPanel({
  agentId,
  agent: _agent,
  meta,
  onToolsSaved,
}: ToolAssemblyPanelProps) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<ViewTab>('tools');
  const [tools, setTools] = useState<ToolConfig[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState>({ description: '', detailed_description: '' });
  const [dirty, setDirty] = useState(false);

  // MCP add server form
  const [showAddServer, setShowAddServer] = useState(false);
  const [newServerName, setNewServerName] = useState('');
  const [newServerUrl, setNewServerUrl] = useState('');
  const [newServerApiKey, setNewServerApiKey] = useState('');
  const [addingServer, setAddingServer] = useState(false);
  const [syncingServerId, setSyncingServerId] = useState<string | null>(null);

  const maxTokens = meta ? Math.floor(meta.context_window_tokens * 0.05) : 10_000;

  // ── Load data ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    Promise.all([
      listAgentTools(agentId),
      listMcpServers(agentId),
    ])
      .then(([t, s]) => { setTools(t); setMcpServers(s); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [open, agentId]);

  // ── Derived state ──────────────────────────────────────────────────────
  const nativeTools = useMemo(() => tools.filter(t => t.source !== 'mcp'), [tools]);
  const mcpTools = useMemo(() => tools.filter(t => t.source === 'mcp'), [tools]);

  const totalTokens = useMemo(
    () => tools.filter(t => t.enabled).reduce((sum, t) => sum + (t.estimated_tokens || estimateToolTokens(t)), 0),
    [tools]
  );

  const budgetPct = maxTokens > 0 ? Math.min(1, totalTokens / maxTokens) : 0;
  const budgetOverLimit = totalTokens > maxTokens;
  const editingTool = tools.find(t => t.id === editingToolId) ?? null;
  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

  // Map server IDs to names for badges
  const serverNameMap = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of mcpServers) m[s.id] = s.name;
    return m;
  }, [mcpServers]);

  // ── Tool handlers ──────────────────────────────────────────────────────

  const handleToggle = useCallback((toolId: string) => {
    setTools(prev => prev.map(t => t.id === toolId ? { ...t, enabled: !t.enabled } : t));
    setDirty(true);
  }, []);

  const handleEdit = useCallback((tool: ToolConfig) => {
    setEditingToolId(tool.id);
    setEditState({
      description: tool.description,
      detailed_description: tool.detailed_description ?? '',
    });
  }, []);

  const handleCancelEdit = useCallback(() => setEditingToolId(null), []);

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

  const handleReset = useCallback(async (tool: ToolConfig) => {
    try {
      const resetTool = await resetAgentTool(agentId, tool.id);
      setTools(prev => prev.map(t => t.id === tool.id ? resetTool : t));
      setDirty(true);
    } catch (e) {
      console.error('Reset failed', e);
    }
  }, [agentId]);

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

  // ── MCP server handlers ────────────────────────────────────────────────

  const handleAddServer = useCallback(async () => {
    if (!newServerName.trim() || !newServerUrl.trim()) return;
    setAddingServer(true);
    try {
      const server = await createMcpServer(agentId, {
        name: newServerName.trim(),
        url: newServerUrl.trim(),
        api_key: newServerApiKey.trim() || null,
      });
      setMcpServers(prev => [...prev, server]);
      setNewServerName('');
      setNewServerUrl('');
      setNewServerApiKey('');
      setShowAddServer(false);
    } catch (e) {
      console.error('Add MCP server failed', e);
    } finally {
      setAddingServer(false);
    }
  }, [agentId, newServerName, newServerUrl, newServerApiKey]);

  const handleSyncServer = useCallback(async (serverId: string) => {
    setSyncingServerId(serverId);
    try {
      await syncMcpServer(serverId);
      // Refresh tools + servers to pick up newly discovered tools.
      const [updatedTools, updatedServers] = await Promise.all([
        listAgentTools(agentId),
        listMcpServers(agentId),
      ]);
      setTools(updatedTools);
      setMcpServers(updatedServers);
    } catch (e) {
      // Still refresh to get updated error status.
      const updatedServers = await listMcpServers(agentId).catch(() => mcpServers);
      setMcpServers(updatedServers);
      console.error('Sync failed', e);
    } finally {
      setSyncingServerId(null);
    }
  }, [agentId, mcpServers]);

  const handleDeleteServer = useCallback(async (serverId: string) => {
    try {
      await deleteMcpServer(serverId);
      setMcpServers(prev => prev.filter(s => s.id !== serverId));
      setTools(prev => prev.filter(t => t.mcp_server_id !== serverId));
    } catch (e) {
      console.error('Delete MCP server failed', e);
    }
  }, []);

  const handleToggleServer = useCallback(async (server: McpServer) => {
    try {
      const updated = await updateMcpServer(server.id, { enabled: !server.enabled });
      setMcpServers(prev => prev.map(s => s.id === server.id ? updated : s));
    } catch (e) {
      console.error('Toggle MCP server failed', e);
    }
  }, []);

  // ── Tool row renderer ──────────────────────────────────────────────────

  const renderToolRow = (tool: ToolConfig) => {
    const tok = tool.estimated_tokens || estimateToolTokens(tool);
    const pct = maxTokens > 0 ? tok / maxTokens : 0;
    const isMcp = tool.source === 'mcp';
    const serverName = isMcp && tool.mcp_server_id ? serverNameMap[tool.mcp_server_id] : null;

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
          {tool.enabled ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <code className="text-xs font-mono font-medium text-[var(--text-primary)] truncate">
              {tool.tool_name}
            </code>
            {/* Source badge */}
            {isMcp ? (
              <span className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Plug className="w-2.5 h-2.5" />
                {serverName ?? 'MCP'}
              </span>
            ) : (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/20">
                native
              </span>
            )}
            <span className="text-xs font-mono text-[var(--color-primary)] tabular-nums flex-shrink-0">
              ~{fmt(tok)} tok
            </span>
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
          {!isMcp && (
            <button
              type="button"
              className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--text-muted)] transition-colors"
              title="Reset to default"
              onClick={() => handleReset(tool)}
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    );
  };

  // ── Render ─────────────────────────────────────────────────────────────

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
        <span className="text-sm font-semibold text-[var(--color-primary)]">Tool Builder</span>
        {tools.length > 0 && (
          <span className="text-xs text-[var(--color-primary)] ml-1">
            ({tools.filter(t => t.enabled).length}/{tools.length} enabled
            {mcpServers.length > 0 && ` · ${mcpServers.length} server${mcpServers.length > 1 ? 's' : ''}`})
          </span>
        )}
        {tools.length > 0 && (
          <span className={`ml-2 text-xs font-mono ${budgetOverLimit ? 'text-[var(--color-danger)]' : 'text-[var(--color-primary)]'}`}>
            {fmt(totalTokens)} / {fmt(maxTokens)} tok
          </span>
        )}
        {dirty && (
          <span className="ml-2 text-xs text-[var(--color-warning)] font-medium">unsaved</span>
        )}
      </button>

      {/* Body */}
      {open && (
        <div className="border-t border-[var(--color-primary)]/20">

          {/* Tab bar */}
          <div className="flex border-b border-[var(--color-primary)]/10">
            <button
              type="button"
              onClick={() => setActiveTab('tools')}
              className={`flex-1 text-xs py-2 font-medium transition-colors ${
                activeTab === 'tools'
                  ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              <span className="flex items-center justify-center gap-1.5">
                <Wrench className="w-3 h-3" />
                Tools ({tools.length})
              </span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('servers')}
              className={`flex-1 text-xs py-2 font-medium transition-colors ${
                activeTab === 'servers'
                  ? 'text-purple-400 border-b-2 border-purple-400'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              <span className="flex items-center justify-center gap-1.5">
                <Server className="w-3 h-3" />
                MCP Servers ({mcpServers.length})
              </span>
            </button>
          </div>

          {/* Budget bar (visible on tools tab) */}
          {activeTab === 'tools' && (
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
          )}

          {/* Save error */}
          {saveError && (
            <div className="mx-3 mt-2 bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-xs rounded-lg px-3 py-2 flex items-center justify-between">
              {saveError}
              <button type="button" className="underline ml-2" onClick={() => setSaveError(null)}>dismiss</button>
            </div>
          )}

          {/* Inline editor */}
          {editingTool && activeTab === 'tools' && (
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
                <button type="button" onClick={handleCancelEdit}
                  className="text-xs px-2.5 py-1 rounded border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                  Cancel
                </button>
                <button type="button" onClick={handleSaveEdit}
                  className="text-xs px-2.5 py-1 rounded bg-[var(--color-primary)] text-white hover:opacity-90">
                  Apply
                </button>
              </div>
            </div>
          )}

          {/* ═══ TOOLS TAB ═══ */}
          {activeTab === 'tools' && (
            <>
              {loading ? (
                <div className="text-sm text-[var(--text-muted)] py-6 text-center">Loading tools…</div>
              ) : (
                <div className="max-h-96 overflow-y-auto">
                  {/* Native tools section */}
                  {nativeTools.length > 0 && (
                    <>
                      <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] bg-[var(--surface-card)]">
                        Native Tools ({nativeTools.filter(t => t.enabled).length}/{nativeTools.length})
                      </div>
                      <div className="divide-y divide-[var(--color-primary)]/10">
                        {nativeTools.map(renderToolRow)}
                      </div>
                    </>
                  )}

                  {/* MCP tools section */}
                  {mcpTools.length > 0 && (
                    <>
                      <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-purple-400 bg-purple-500/5 border-t border-[var(--color-primary)]/10">
                        <span className="flex items-center gap-1">
                          <Plug className="w-2.5 h-2.5" />
                          MCP Tools ({mcpTools.filter(t => t.enabled).length}/{mcpTools.length})
                        </span>
                      </div>
                      <div className="divide-y divide-[var(--color-primary)]/10">
                        {mcpTools.map(renderToolRow)}
                      </div>
                    </>
                  )}

                  {tools.length === 0 && !loading && (
                    <div className="text-sm text-[var(--text-muted)] py-6 text-center">
                      No tools configured. Add an MCP server to discover tools.
                    </div>
                  )}
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
                    className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
                      budgetOverLimit
                        ? 'bg-[var(--surface-muted)] text-[var(--text-muted)] cursor-not-allowed'
                        : 'bg-[var(--color-primary)] text-white hover:opacity-90 disabled:opacity-50'
                    }`}
                    title={budgetOverLimit ? 'Tool descriptions exceed budget' : undefined}
                  >
                    <Save className="w-3 h-3" />
                    {saving ? 'Saving…' : 'Save Tools'}
                  </button>
                </div>
              )}
            </>
          )}

          {/* ═══ MCP SERVERS TAB ═══ */}
          {activeTab === 'servers' && (
            <div className="divide-y divide-[var(--color-primary)]/10">
              {/* Server list */}
              {mcpServers.map((server) => {
                const isSyncing = syncingServerId === server.id;
                const statusColor = server.status === 'connected' ? 'text-green-400'
                  : server.status === 'error' ? 'text-[var(--color-danger)]'
                  : 'text-[var(--text-muted)]';
                return (
                  <div key={server.id} className="px-3 py-2.5 group">
                    <div className="flex items-center gap-2">
                      {/* Status dot */}
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        server.status === 'connected' ? 'bg-green-400'
                        : server.status === 'error' ? 'bg-[var(--color-danger)]'
                        : 'bg-[var(--text-muted)]'
                      }`} />
                      {/* Name + URL */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-[var(--text-primary)]">{server.name}</span>
                          <span className={`text-[10px] ${statusColor}`}>{server.status}</span>
                          {server.tool_count > 0 && (
                            <span className="text-[10px] text-purple-400">{server.tool_count} tools</span>
                          )}
                          {server.has_api_key && (
                            <span className="text-[10px] text-[var(--text-muted)]">🔑</span>
                          )}
                        </div>
                        <p className="text-[10px] text-[var(--text-muted)] truncate">{server.url}</p>
                        {server.status === 'error' && server.status_detail && (
                          <p className="text-[10px] text-[var(--color-danger)] mt-0.5 truncate">{server.status_detail}</p>
                        )}
                      </div>
                      {/* Actions */}
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-[var(--color-primary)]/10 text-[var(--color-primary)] transition-colors"
                          title={server.enabled ? 'Disable server' : 'Enable server'}
                          onClick={() => handleToggleServer(server)}
                        >
                          {server.enabled
                            ? <Plug className="w-3.5 h-3.5" />
                            : <Unplug className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                          }
                        </button>
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-purple-500/10 text-purple-400 transition-colors disabled:opacity-50"
                          title="Sync tools from server"
                          onClick={() => handleSyncServer(server.id)}
                          disabled={isSyncing}
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-[var(--color-danger)]/10 text-[var(--color-danger)] transition-colors opacity-0 group-hover:opacity-100"
                          title="Remove server"
                          onClick={() => handleDeleteServer(server.id)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}

              {mcpServers.length === 0 && !showAddServer && (
                <div className="py-8 text-center">
                  <Server className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2 opacity-50" />
                  <p className="text-xs text-[var(--text-muted)]">No MCP servers connected</p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Add a server to discover and use external tools</p>
                </div>
              )}

              {/* Add server form */}
              {showAddServer ? (
                <div className="px-3 py-3 bg-[var(--surface-card)] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[var(--text-primary)]">Add MCP Server</span>
                    <button type="button" onClick={() => setShowAddServer(false)}
                      className="p-1 hover:bg-[var(--surface-hover)] rounded text-[var(--text-muted)]">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Server name (e.g. GitHub)"
                    className="w-full text-xs border border-[var(--border-color)] rounded p-1.5 focus:ring-1 focus:ring-purple-400 focus:outline-none bg-transparent"
                    value={newServerName}
                    onChange={e => setNewServerName(e.target.value)}
                  />
                  <input
                    type="text"
                    placeholder="SSE endpoint URL (e.g. https://mcp.example.com/sse)"
                    className="w-full text-xs border border-[var(--border-color)] rounded p-1.5 focus:ring-1 focus:ring-purple-400 focus:outline-none bg-transparent"
                    value={newServerUrl}
                    onChange={e => setNewServerUrl(e.target.value)}
                  />
                  <input
                    type="password"
                    placeholder="API key (optional)"
                    className="w-full text-xs border border-[var(--border-color)] rounded p-1.5 focus:ring-1 focus:ring-purple-400 focus:outline-none bg-transparent"
                    value={newServerApiKey}
                    onChange={e => setNewServerApiKey(e.target.value)}
                  />
                  <div className="flex gap-2 justify-end">
                    <button type="button" onClick={() => setShowAddServer(false)}
                      className="text-xs px-2.5 py-1 rounded border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={addingServer || !newServerName.trim() || !newServerUrl.trim()}
                      onClick={handleAddServer}
                      className="text-xs px-2.5 py-1 rounded bg-purple-500 text-white hover:opacity-90 disabled:opacity-50"
                    >
                      {addingServer ? 'Adding…' : 'Add Server'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => setShowAddServer(true)}
                    className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add MCP Server
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
