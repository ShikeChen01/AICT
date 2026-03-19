/**
 * Desktops Page — Grid-first live desktop viewer.
 *
 * Desktops are user-managed, persistent VNC-capable environments.
 * Sandboxes (headless, agent-owned) are not shown here.
 *
 * Default view: responsive grid of live desktop thumbnails (MJPEG streams).
 * Click a desktop → expand to full interactive VNC mode.
 * Assign / unassign / reassign desktops to agents via dropdown.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  Monitor,
  X,
  Settings2,
  RotateCcw,
  Trash2,
  Eye,
  MousePointer2,
  Maximize2,
  Plus,
  Link2,
  Unlink,
} from 'lucide-react';
import {
  getProject,
  getAgents,
  listSandboxes,
  listSandboxConfigs,
  createDesktop,
  assignSandbox,
  unassignSandbox,
  restartSandbox,
  destroySandbox,
  updateSandbox,
  applySandboxConfig,
  restoreSandboxSnapshot,
  listSandboxSnapshots,
} from '../api/client';
import type { Project, Agent, SandboxConfig, Sandbox, SandboxSnapshot } from '../types';
import { AppLayout } from '../components/Layout';
import { useScreenStream } from '../hooks/useScreenStream';
import { VncView } from '../components/ScreenStream';

// ── Constants ──────────────────────────────────────────────────────────────

const STATUS_BG: Record<string, string> = {
  assigned: 'bg-green-500/20 text-green-400',
  idle: 'bg-gray-500/20 text-gray-400',
  resetting: 'bg-amber-500/20 text-amber-400',
  unhealthy: 'bg-red-500/20 text-red-400',
};

// ── Page Shell ─────────────────────────────────────────────────────────────

export function SandboxPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId)
      .then(setProject)
      .catch(() => setProject(null))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center" role="status">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" />
        </div>
      </AppLayout>
    );
  }

  if (!project || !projectId) {
    return (
      <AppLayout>
        <div className="flex flex-col flex-1 items-center justify-center gap-4">
          <AlertCircle className="w-12 h-12 text-[var(--color-danger)]" />
          <button onClick={() => navigate('/projects')} className="text-[var(--color-primary)] hover:underline">
            Back to Projects
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <DesktopContent projectId={projectId} />
    </AppLayout>
  );
}

// ── Desktop Content ───────────────────────────────────────────────────────

function DesktopContent({ projectId }: { projectId: string }) {
  const [allSandboxes, setAllSandboxes] = useState<Sandbox[]>([]);
  const [configs, setConfigs] = useState<SandboxConfig[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Expanded VNC state
  const [expandedDesktopId, setExpandedDesktopId] = useState<string | null>(null);
  const [expandedInteractive, setExpandedInteractive] = useState(true);

  // Config modal
  const [configModalDesktop, setConfigModalDesktop] = useState<Sandbox | null>(null);

  const refreshInterval = useRef<number | undefined>(undefined);

  const fetchData = useCallback(async () => {
    try {
      const [agentList, sandboxList, configList] = await Promise.all([
        getAgents(projectId),
        listSandboxes(projectId).catch(() => [] as Sandbox[]),
        listSandboxConfigs().catch(() => [] as SandboxConfig[]),
      ] as const);

      setAgents(agentList);
      setConfigs(configList);
      setAllSandboxes(sandboxList);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load desktops');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
    refreshInterval.current = setInterval(fetchData, 10000);
    return () => { if (refreshInterval.current) clearInterval(refreshInterval.current); };
  }, [fetchData]);

  // Only show desktops, not headless sandboxes
  const desktops = allSandboxes.filter(sb => sb.unit_type === 'desktop');

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-primary)]" />
        <span className="ml-2 text-sm text-[var(--text-muted)]">Loading desktops…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="rounded-xl border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] p-4 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      </div>
    );
  }

  // ── Full VNC Expanded View ───────────────────────────────────
  if (expandedDesktopId) {
    const desktop = desktops.find(d => d.id === expandedDesktopId);
    return (
      <div className="flex flex-1 flex-col min-h-0 bg-black">
        {/* Top bar */}
        <div className="flex items-center gap-3 px-4 py-2 bg-[var(--surface-card)] border-b border-[var(--border-color)]">
          <button
            onClick={() => setExpandedDesktopId(null)}
            className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <X className="w-4 h-4" />
            Back to Grid
          </button>
          <div className="flex-1" />
          {desktop && (
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {desktop.name ?? 'Desktop'}{desktop.agent_name ? ` — ${desktop.agent_name}` : ''}
            </span>
          )}
          <div className="flex-1" />
          <button
            onClick={() => setExpandedInteractive(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
              ${expandedInteractive
                ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'
              }`}
          >
            {expandedInteractive ? <MousePointer2 className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            {expandedInteractive ? 'Interactive' : 'View Only'}
          </button>
        </div>

        {/* VNC */}
        <div className="flex-1 min-h-0">
          {desktop && (
            <VncView
              sandboxId={desktop.orchestrator_sandbox_id}
              viewOnly={!expandedInteractive}
            />
          )}
        </div>
      </div>
    );
  }

  // ── Grid View ────────────────────────────────────────────────
  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden bg-[var(--app-bg)]">
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-[var(--text-primary)]">Desktops</h1>
              <p className="text-sm text-[var(--text-muted)] mt-0.5">
                {desktops.length} desktop{desktops.length !== 1 ? 's' : ''} · Click to enter remote desktop
              </p>
            </div>
            <CreateDesktopButton projectId={projectId} onCreated={fetchData} />
          </div>

          {/* Grid */}
          {desktops.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--surface-muted)] p-12 text-center">
              <Monitor className="w-10 h-10 mx-auto text-[var(--text-faint)] mb-3" />
              <p className="text-sm text-[var(--text-muted)] mb-1">No desktops running</p>
              <p className="text-xs text-[var(--text-faint)]">Create a desktop to get started.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {desktops.map(desktop => (
                <DesktopCard
                  key={desktop.id}
                  desktop={desktop}
                  agents={agents}
                  desktops={desktops}
                  configs={configs}
                  onExpand={() => setExpandedDesktopId(desktop.id)}
                  onConfigure={() => setConfigModalDesktop(desktop)}
                  onRefresh={fetchData}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Config Modal */}
      {configModalDesktop && (
        <ConfigModal
          sandbox={configModalDesktop}
          configs={configs}
          onClose={() => setConfigModalDesktop(null)}
          onSaved={() => { setConfigModalDesktop(null); fetchData(); }}
        />
      )}
    </div>
  );
}

// ── Desktop Card ──────────────────────────────────────────────────────────

interface DesktopCardProps {
  desktop: Sandbox;
  agents: Agent[];
  desktops: Sandbox[];
  configs: SandboxConfig[];
  onExpand: () => void;
  onConfigure: () => void;
  onRefresh: () => void;
}

function DesktopCard({ desktop, agents, desktops, onExpand, onConfigure, onRefresh }: DesktopCardProps) {
  const { frameUrl, isConnected } = useScreenStream(desktop.orchestrator_sandbox_id);
  const statusClass = STATUS_BG[desktop.status] ?? STATUS_BG.idle;
  const [acting, setActing] = useState(false);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [snapshots, setSnapshots] = useState<SandboxSnapshot[]>([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [showAgentDropdown, setShowAgentDropdown] = useState(false);
  const agentDropdownRef = useRef<HTMLDivElement>(null);

  // One agent can only have one desktop — filter out agents already assigned to another desktop
  const assignableAgents = agents.filter(
    a => a.id === desktop.agent_id || !desktops.some(d => d.agent_id === a.id),
  );

  const handleAction = async (action: () => Promise<unknown>) => {
    setActing(true);
    try { await action(); onRefresh(); }
    finally { setActing(false); }
  };

  const handleLoadSnapshots = async () => {
    if (showSnapshots) {
      setShowSnapshots(false);
      return;
    }
    setLoadingSnapshots(true);
    try {
      const snaps = await listSandboxSnapshots(desktop.id);
      setSnapshots(snaps);
      setShowSnapshots(true);
    } catch (e) {
      console.error('Failed to load snapshots:', e);
    } finally {
      setLoadingSnapshots(false);
    }
  };

  const handleAssign = async (agentId: string) => {
    setShowAgentDropdown(false);
    await handleAction(async () => {
      if (desktop.agent_id) {
        await unassignSandbox(desktop.id);
      }
      await assignSandbox(desktop.id, agentId);
    });
  };

  const handleUnassign = async () => {
    await handleAction(() => unassignSandbox(desktop.id));
  };

  // Close agent dropdown on outside click — only listen when open
  useEffect(() => {
    if (!showAgentDropdown) return;
    const handleClick = (e: MouseEvent) => {
      if (agentDropdownRef.current && !agentDropdownRef.current.contains(e.target as Node)) {
        setShowAgentDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showAgentDropdown]);

  return (
    <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] overflow-hidden hover:border-[var(--border-color-hover)] transition-colors group">
      {/* Stream preview */}
      <button type="button" onClick={onExpand} className="relative w-full aspect-video cursor-pointer overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)' }}>
        {frameUrl ? (
          <img src={frameUrl} alt={`${desktop.name ?? 'Desktop'} display`} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
            <Monitor className="w-8 h-8 text-slate-500" />
            <span className="text-[10px] text-slate-500 font-medium">
              {isConnected ? 'Waiting for display…' : 'Connecting…'}
            </span>
          </div>
        )}
        {/* Hover overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          <Maximize2 className="w-6 h-6 text-white/90" />
        </div>
        {/* Connection dot */}
        <div className={`absolute top-2 right-2 w-2.5 h-2.5 rounded-full ring-2 ring-black/20 ${isConnected ? 'bg-green-400' : 'bg-gray-500 animate-pulse'}`} />
      </button>

      {/* Info bar */}
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-sm font-medium text-[var(--text-primary)] truncate flex-1">
            {desktop.name ?? 'Desktop'}
          </span>
          <span className={`text-[10px] font-medium rounded px-1.5 py-0.5 ${statusClass}`}>
            {desktop.status}
          </span>
        </div>

        {/* Agent assignment */}
        <div className="flex items-center gap-2 mb-2" ref={agentDropdownRef}>
          {desktop.agent_id ? (
            <div className="flex items-center gap-1.5 flex-1 min-w-0">
              <Link2 className="w-3 h-3 text-[var(--color-primary)] shrink-0" />
              <span className="text-[11px] text-[var(--text-secondary)] truncate">{desktop.agent_name}</span>
              <button
                onClick={handleUnassign}
                disabled={acting}
                title="Unassign agent"
                className="p-0.5 rounded text-[var(--text-faint)] hover:text-[var(--color-danger)] transition-colors disabled:opacity-40 shrink-0"
              >
                <Unlink className="w-3 h-3" />
              </button>
            </div>
          ) : (
            <div className="relative flex-1">
              <button
                onClick={() => setShowAgentDropdown(v => !v)}
                disabled={acting}
                className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-40"
              >
                <Link2 className="w-3 h-3" />
                Assign to agent…
              </button>
              {showAgentDropdown && (
                <div className="absolute left-0 top-full mt-1 w-48 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] shadow-lg z-20 py-1">
                  {assignableAgents.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-[var(--text-faint)]">No available agents</div>
                  ) : (
                    assignableAgents.map(a => (
                      <button
                        key={a.id}
                        onClick={() => handleAssign(a.id)}
                        className="w-full text-left px-3 py-1.5 text-xs text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
                      >
                        <span className="font-medium">{a.display_name}</span>
                        <span className="text-[var(--text-muted)] ml-1.5 capitalize">({a.role})</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* Reassign dropdown (when already assigned) */}
          {desktop.agent_id && (
            <div className="relative">
              <button
                onClick={() => setShowAgentDropdown(v => !v)}
                disabled={acting}
                title="Reassign to different agent"
                className="p-0.5 rounded text-[var(--text-faint)] hover:text-[var(--color-primary)] transition-colors disabled:opacity-40"
              >
                <Link2 className="w-3 h-3" />
              </button>
              {showAgentDropdown && (
                <div className="absolute right-0 top-full mt-1 w-48 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] shadow-lg z-20 py-1">
                  {assignableAgents.filter(a => a.id !== desktop.agent_id).length === 0 ? (
                    <div className="px-3 py-2 text-xs text-[var(--text-faint)]">No other agents</div>
                  ) : (
                    assignableAgents.filter(a => a.id !== desktop.agent_id).map(a => (
                      <button
                        key={a.id}
                        onClick={() => handleAssign(a.id)}
                        className="w-full text-left px-3 py-1.5 text-xs text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
                      >
                        <span className="font-medium">{a.display_name}</span>
                        <span className="text-[var(--text-muted)] ml-1.5 capitalize">({a.role})</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)] mb-2">
          <span className="font-mono">{desktop.orchestrator_sandbox_id.slice(0, 12)}</span>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-wrap">
          <button
            onClick={onConfigure}
            title="Configure"
            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleAction(() => restartSandbox(desktop.id))}
            disabled={acting}
            title="Restart"
            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleAction(() => destroySandbox(desktop.id))}
            disabled={acting}
            title="Destroy"
            className="p-1.5 rounded-md text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 transition-colors disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <div className="flex-1" />
        </div>

        {/* Snapshots */}
        <div className="mt-2 space-y-1">
          <button
            onClick={handleLoadSnapshots}
            disabled={loadingSnapshots}
            className="text-[10px] font-medium px-2 py-1 rounded-md border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40 w-full"
          >
            {loadingSnapshots ? 'Loading…' : showSnapshots ? 'Hide Snapshots' : 'Snapshots'}
          </button>
          {showSnapshots && snapshots.length > 0 && (
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {snapshots.map(snap => (
                <button
                  key={snap.id}
                  onClick={() => handleAction(() => restoreSandboxSnapshot(desktop.id, snap.id))}
                  disabled={acting}
                  className="w-full text-left text-[9px] px-2 py-0.5 rounded border border-[var(--border-color-subtle)] bg-[var(--surface-muted)] text-[var(--text-muted)] hover:bg-[var(--color-primary)]/20 transition-colors disabled:opacity-40 truncate"
                  title={snap.label ?? snap.id}
                >
                  {snap.label || snap.id.slice(0, 8)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Create Desktop Button ─────────────────────────────────────────────────

function CreateDesktopButton({ projectId, onCreated }: { projectId: string; onCreated: () => void }) {
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      await createDesktop(projectId);
      onCreated();
    } catch (err) {
      console.error('Failed to create desktop:', err);
      setError(err instanceof Error ? err.message : 'Failed to create desktop');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleCreate}
        disabled={creating}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] transition-colors disabled:opacity-50"
      >
        <Plus className="w-4 h-4" />
        {creating ? 'Creating…' : 'New Desktop'}
      </button>
      {error && (
        <div className="absolute right-0 mt-1 w-72 rounded-lg border border-red-500/30 bg-red-950/80 shadow-lg z-20 p-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-red-300">Failed to create desktop</p>
              <p className="text-[10px] text-red-400/70 mt-1 break-words">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="text-red-400/60 hover:text-red-300 shrink-0">
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Config Modal ───────────────────────────────────────────────────────────

interface ConfigModalProps {
  sandbox: Sandbox;
  configs: SandboxConfig[];
  onClose: () => void;
  onSaved: () => void;
}

function ConfigModal({ sandbox, configs, onClose, onSaved }: ConfigModalProps) {
  const [selectedConfigId, setSelectedConfigId] = useState<string>(sandbox.sandbox_config_id ?? '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSandbox(sandbox.id, { config_id: selectedConfigId || null });
      if (selectedConfigId) {
        await applySandboxConfig(sandbox.id);
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-[var(--surface-card)] rounded-xl border border-[var(--border-color)] shadow-xl w-full max-w-md p-6"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            Configure: {sandbox.name ?? 'Desktop'}
          </h3>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-3">
          <label className="block">
            <span className="text-sm font-medium text-[var(--text-secondary)]">Desktop Config</span>
            <select
              value={selectedConfigId}
              onChange={e => setSelectedConfigId(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-input)] px-3 py-2 text-sm text-[var(--text-primary)]"
            >
              <option value="">None</option>
              {configs.map(c => (
                <option key={c.id} value={c.id}>{c.name} — {c.os_image}</option>
              ))}
            </select>
          </label>

          <div className="text-[11px] text-[var(--text-faint)]">
            Assigning a config will run the setup script on this desktop. This may take a few minutes.
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] transition-colors disabled:opacity-50"
          >
            {saving ? 'Applying…' : 'Apply Config'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SandboxPage;
