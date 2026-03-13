/**
 * Sandbox Page — Grid-first live sandbox viewer.
 *
 * Default view: responsive grid of live sandbox thumbnails (MJPEG streams).
 * Click a sandbox → expand to full interactive VNC mode.
 * Config gear icon on each sandbox → opens config modal.
 * Toolbar: sandbox lifecycle controls, activity feed toggle.
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
  Power,
  Eye,
  MousePointer2,
  Maximize2,
  ChevronDown,
} from 'lucide-react';
import {
  getProject,
  getAgents,
  listSandboxes,
  listSandboxConfigs,
  claimSandbox,
  releaseSandbox,
  restartSandbox,
  destroySandbox,
  updateSandbox,
  applySandboxConfig,
  assignSandboxConfig,
  restoreSandboxSnapshot,
  listSandboxSnapshots,
} from '../api/client';
import type { Project, Agent, SandboxConfig, Sandbox, SandboxSnapshot } from '../types';
import { AppLayout } from '../components/Layout';
import { useScreenStream } from '../hooks/useScreenStream';
import { VncView } from '../components/ScreenStream';

// ── Constants ──────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  manager: '#f59e0b',
  cto: '#8b5cf6',
  engineer: '#3b82f6',
};

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
        <div className="flex flex-1 items-center justify-center">
          <AlertCircle className="w-12 h-12 text-[var(--color-danger)] mb-4" />
          <button onClick={() => navigate('/projects')} className="text-[var(--color-primary)] hover:underline">
            Back to Projects
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <SandboxContent projectId={projectId} />
    </AppLayout>
  );
}

// ── Sandbox Content ────────────────────────────────────────────────────────

function SandboxContent({ projectId }: { projectId: string }) {
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [configs, setConfigs] = useState<SandboxConfig[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Expanded VNC state
  const [expandedSandboxId, setExpandedSandboxId] = useState<string | null>(null);
  const [expandedInteractive, setExpandedInteractive] = useState(true);

  // Config modal
  const [configModalSandbox, setConfigModalSandbox] = useState<Sandbox | null>(null);

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
      setSandboxes(sandboxList);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sandboxes');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
    refreshInterval.current = setInterval(fetchData, 10000);
    return () => { if (refreshInterval.current) clearInterval(refreshInterval.current); };
  }, [fetchData]);

  // Agents that don't have a sandbox yet
  const agentsWithoutSandbox = agents.filter(a => !sandboxes.some(sb => sb.agent_id === a.id));

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-primary)]" />
        <span className="ml-2 text-sm text-[var(--text-muted)]">Loading sandboxes…</span>
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
  if (expandedSandboxId) {
    const sb = sandboxes.find(s => s.id === expandedSandboxId);
    return (
      <div className="flex flex-1 flex-col min-h-0 bg-black">
        {/* Top bar */}
        <div className="flex items-center gap-3 px-4 py-2 bg-[var(--surface-card)] border-b border-[var(--border-color)]">
          <button
            onClick={() => setExpandedSandboxId(null)}
            className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <X className="w-4 h-4" />
            Back to Grid
          </button>
          <div className="flex-1" />
          {sb && (
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {sb.agent_name ?? 'Unknown'} — {sb.os_image}
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
          {expandedSandboxId && sb && (
            <VncView
              sandboxId={sb.orchestrator_sandbox_id}
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
              <h1 className="text-xl font-bold text-[var(--text-primary)]">Sandboxes</h1>
              <p className="text-sm text-[var(--text-muted)] mt-0.5">{sandboxes.length} running · Click to enter remote desktop</p>
            </div>
            {agentsWithoutSandbox.length > 0 && (
              <StartSandboxDropdown projectId={projectId} agents={agentsWithoutSandbox} onStarted={fetchData} />
            )}
          </div>

          {/* Grid */}
          {sandboxes.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--surface-muted)] p-12 text-center">
              <Monitor className="w-10 h-10 mx-auto text-[var(--text-faint)] mb-3" />
              <p className="text-sm text-[var(--text-muted)] mb-1">No sandboxes running</p>
              <p className="text-xs text-[var(--text-faint)]">Start a sandbox for an agent to see it here.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {sandboxes.map(sb => (
                <SandboxCard
                  key={sb.id}
                  projectId={projectId}
                  sandbox={sb}
                  configs={configs}
                  onExpand={() => {
                    setExpandedSandboxId(sb.id);
                  }}
                  onConfigure={() => setConfigModalSandbox(sb)}
                  onRefresh={fetchData}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Config Modal */}
      {configModalSandbox && (
        <ConfigModal
          sandbox={configModalSandbox}
          configs={configs}
          onClose={() => setConfigModalSandbox(null)}
          onSaved={() => { setConfigModalSandbox(null); fetchData(); }}
        />
      )}
    </div>
  );
}

// ── Sandbox Card ───────────────────────────────────────────────────────────

interface SandboxCardProps {
  projectId: string;
  sandbox: Sandbox;
  configs: SandboxConfig[];
  onExpand: () => void;
  onConfigure: () => void;
  onRefresh: () => void;
}

function SandboxCard({ projectId, sandbox, onExpand, onConfigure, onRefresh }: SandboxCardProps) {
  const { frameUrl, isConnected } = useScreenStream(sandbox.orchestrator_sandbox_id);
  const roleColor = ROLE_COLORS[sandbox.agent_role ?? 'engineer'] ?? '#64748b';
  const statusClass = STATUS_BG[sandbox.status] ?? STATUS_BG.idle;
  const [acting, setActing] = useState(false);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [snapshots, setSnapshots] = useState<SandboxSnapshot[]>([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);

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
      const snaps = await listSandboxSnapshots(sandbox.id);
      setSnapshots(snaps);
      setShowSnapshots(true);
    } catch (e) {
      console.error('Failed to load snapshots:', e);
    } finally {
      setLoadingSnapshots(false);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] overflow-hidden hover:border-[var(--border-color-hover)] transition-colors group">
      {/* Stream preview */}
      <button type="button" onClick={onExpand} className="relative w-full aspect-video bg-black/90 cursor-pointer">
        {frameUrl ? (
          <img src={frameUrl} alt={`${sandbox.agent_name ?? 'Unknown'} sandbox`} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Monitor className="w-8 h-8 text-[var(--text-faint)]" />
          </div>
        )}
        {/* Hover overlay */}
        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          <Maximize2 className="w-6 h-6 text-white" />
        </div>
        {/* Connection dot */}
        <div className={`absolute top-2 right-2 w-2 h-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-gray-500'}`} />
      </button>

      {/* Info bar */}
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold text-white shrink-0"
            style={{ backgroundColor: roleColor }}>
            {(sandbox.agent_name ?? 'U').charAt(0).toUpperCase()}
          </div>
          <span className="text-sm font-medium text-[var(--text-primary)] truncate flex-1">{sandbox.agent_name ?? 'Unknown'}</span>
          <span className={`text-[10px] font-medium rounded px-1.5 py-0.5 ${statusClass}`}>
            {sandbox.status}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)] mb-2">
          <span className="font-mono">{sandbox.os_image}</span>
          <span className="text-[var(--text-faint)]">·</span>
          <span>{sandbox.persistent ? 'persistent' : 'ephemeral'}</span>
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
            onClick={() => handleAction(() => restartSandbox(sandbox.id))}
            disabled={acting}
            title="Restart"
            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleAction(async () => {
              await releaseSandbox(sandbox.id);
              if (sandbox.agent_id) {
                await claimSandbox(projectId, sandbox.agent_id);
              }
            })}
            disabled={acting}
            title="Reset (fresh)"
            className="p-1.5 rounded-md text-[var(--color-warning)] hover:bg-[var(--color-warning)]/10 transition-colors disabled:opacity-40"
          >
            <Power className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleAction(() => destroySandbox(sandbox.id))}
            disabled={acting}
            title="Destroy"
            className="p-1.5 rounded-md text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 transition-colors disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <div className="flex-1" />
          <button
            onClick={() => handleAction(() => updateSandbox(sandbox.id, { persistent: !sandbox.persistent }))}
            disabled={acting}
            className="text-[10px] font-medium px-2 py-1 rounded-md border border-[var(--border-color)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40"
          >
            {sandbox.persistent ? 'Make Ephemeral' : 'Make Persistent'}
          </button>
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
                  onClick={() => handleAction(() => restoreSandboxSnapshot(sandbox.id, snap.id))}
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

// ── Start Sandbox Dropdown ─────────────────────────────────────────────────

function StartSandboxDropdown({ projectId, agents, onStarted }: { projectId: string; agents: Agent[]; onStarted: () => void }) {
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleStart = async (agentId: string) => {
    setStarting(true);
    try {
      await claimSandbox(projectId, agentId);
      onStarted();
    } catch (err) {
      console.error('Failed to start sandbox:', err);
      alert(err instanceof Error ? err.message : 'Failed to start sandbox');
    } finally {
      setStarting(false);
      setOpen(false);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] transition-colors"
      >
        <Power className="w-4 h-4" />
        Start Sandbox
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-56 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] shadow-lg z-20 py-1">
          {agents.map(a => (
            <button
              key={a.id}
              onClick={() => handleStart(a.id)}
              disabled={starting}
              className="w-full text-left px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-40"
            >
              <span className="font-medium">{a.display_name}</span>
              <span className="text-[var(--text-muted)] ml-2 capitalize">({a.role})</span>
            </button>
          ))}
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
      if (sandbox.agent_id) {
        await assignSandboxConfig(sandbox.agent_id, selectedConfigId || null);
      }
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
            Configure: {sandbox.agent_name ?? 'Sandbox'}
          </h3>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-3">
          <label className="block">
            <span className="text-sm font-medium text-[var(--text-secondary)]">Sandbox Config</span>
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
            Assigning a config will run the setup script on this sandbox. This may take a few minutes.
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
