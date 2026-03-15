/**
 * Dashboard Page — Project Command Center.
 *
 * The primary landing page showing at-a-glance project health:
 *  • Budget & cost controls (daily spend, rate limits)
 *  • Emergency stop-all button
 *  • Agent fleet overview (compact cards)
 *  • Live sandbox thumbnails (click to enter Sandbox page)
 *  • Recent activity log (compact feed)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  Bot,
  BrainCircuit,
  Cpu,
  DollarSign,
  Activity,
  OctagonX,
  Monitor,
  ChevronRight,
  Zap,
  TrendingUp,
  Clock,
  Shield,
} from 'lucide-react';
import {
  getProject,
  getAgents,
  getAgentStatuses,
  getProjectUsage,
  getProjectSettings,
  listSandboxes,
  stopAgent,
} from '../api/client';
import type {
  Project,
  Agent,
  AgentStatusWithQueue,
  ProjectUsageResponse,
  ProjectSettings,
  Sandbox,
} from '../types';
import { AppLayout } from '../components/Layout';
import { useScreenStream } from '../hooks/useScreenStream';

// ── Constants ──────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  manager: '#f59e0b',
  cto: '#8b5cf6',
  engineer: '#3b82f6',
};

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  busy: '#f59e0b',
  sleeping: '#64748b',
};

// ── Page Shell ─────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchProject = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const proj = await getProject(projectId);
      setProject(proj);
    } catch {
      setProject(null);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center" role="status">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" aria-hidden="true" />
          <span className="sr-only">Loading dashboard…</span>
        </div>
      </AppLayout>
    );
  }

  if (!project || !projectId) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <AlertCircle className="w-12 h-12 mx-auto text-[var(--color-danger)] mb-4" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Project not found</h2>
            <button onClick={() => navigate('/projects')} className="mt-4 text-[var(--color-primary)] hover:underline">
              Back to Projects
            </button>
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="flex flex-1 flex-col min-h-0 overflow-hidden bg-[var(--app-bg)]">
        <div className="h-full overflow-y-auto">
          <main className="max-w-[1400px] mx-auto px-6 py-6">
            <DashboardContent projectId={projectId} projectName={project.name} />
          </main>
        </div>
      </div>
    </AppLayout>
  );
}

// ── Dashboard Content ──────────────────────────────────────────────────────

interface DashboardContentProps {
  projectId: string;
  projectName: string;
}

function DashboardContent({ projectId, projectName }: DashboardContentProps) {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [statuses, setStatuses] = useState<AgentStatusWithQueue[]>([]);
  const [usage, setUsage] = useState<ProjectUsageResponse | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stoppingAll, setStoppingAll] = useState(false);
  const cacheRef = useRef<{ data: Sandbox[]; timestamp: number } | null>(null);
  const refreshInterval = useRef<number | undefined>(undefined);

  const fetchData = useCallback(async () => {
    try {
      const [agentList, statusList, usageData, settingsData, sandboxList] = await Promise.all([
        getAgents(projectId),
        getAgentStatuses(projectId).catch(() => [] as AgentStatusWithQueue[]),
        getProjectUsage(projectId).catch(() => null as ProjectUsageResponse | null),
        getProjectSettings(projectId).catch(() => null as ProjectSettings | null),
        listSandboxes(projectId).catch(() => [] as Sandbox[]),
      ] as const);

      setAgents(agentList);
      setStatuses(statusList);
      setUsage(usageData);
      setSettings(settingsData);
      setSandboxes(sandboxList);
      cacheRef.current = { data: sandboxList, timestamp: Date.now() };
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
    refreshInterval.current = setInterval(fetchData, 15000);
    return () => { if (refreshInterval.current) clearInterval(refreshInterval.current); };
  }, [fetchData]);

  const handleStopAll = async () => {
    if (stoppingAll) return;
    setStoppingAll(true);
    try {
      const active = agents.filter(a => a.status === 'active' || a.status === 'busy');
      await Promise.allSettled(active.map(a => stopAgent(a.id)));
      await fetchData();
    } finally {
      setStoppingAll(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-primary)]" aria-hidden="true" />
        <span className="ml-2 text-sm text-[var(--text-muted)]">Loading command center…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] p-4 text-sm text-[var(--color-danger)]" role="alert">
        {error}
      </div>
    );
  }

  const statusMap = new Map(statuses.map(s => [s.id, s]));
  const activeAgents = agents.filter(a => a.status === 'active' || a.status === 'busy');
  const totalCostToday = usage?.today.estimated_cost_usd ?? 0;
  const dailyBudget = settings?.daily_cost_budget_usd ?? 0;
  const budgetPct = dailyBudget > 0 ? Math.min(100, (totalCostToday / dailyBudget) * 100) : 0;
  const totalTokensToday = usage?.today.total_input_tokens ?? 0;
  const totalOutputToday = usage?.today.total_output_tokens ?? 0;
  const callsLastHour = usage?.last_hour.total_calls ?? 0;

  return (
    <div className="space-y-6">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)]">{projectName}</h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">Project Command Center</p>
        </div>
        <button
          type="button"
          onClick={handleStopAll}
          disabled={stoppingAll || activeAgents.length === 0}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all
            bg-red-500/10 text-red-400 border border-red-500/20
            hover:bg-red-500/20 hover:border-red-500/40
            disabled:opacity-40 disabled:cursor-not-allowed"
          title={activeAgents.length === 0 ? 'No active agents' : `Stop ${activeAgents.length} active agent(s)`}
        >
          <OctagonX className="w-4 h-4" aria-hidden="true" />
          {stoppingAll ? 'Stopping…' : `Emergency Stop All (${activeAgents.length})`}
        </button>
      </div>

      {/* ── Budget & Cost Row ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <StatCard
          icon={<DollarSign className="w-4 h-4" />}
          label="Cost Today"
          value={`$${totalCostToday.toFixed(4)}`}
          sub={dailyBudget > 0 ? `of $${dailyBudget.toFixed(2)} budget` : 'no budget set'}
          accent={budgetPct > 80 ? 'danger' : budgetPct > 50 ? 'warning' : 'success'}
          progress={dailyBudget > 0 ? budgetPct : undefined}
        />
        <StatCard
          icon={<TrendingUp className="w-4 h-4" />}
          label="Tokens Today"
          value={formatNumber(totalTokensToday + totalOutputToday)}
          sub={`${formatNumber(totalTokensToday)} in · ${formatNumber(totalOutputToday)} out`}
          accent="primary"
        />
        <StatCard
          icon={<Zap className="w-4 h-4" />}
          label="Calls (Last Hour)"
          value={String(callsLastHour)}
          sub={settings?.calls_per_hour_limit ? `limit: ${settings.calls_per_hour_limit}/hr` : 'no rate limit'}
          accent="primary"
        />
        <StatCard
          icon={<Shield className="w-4 h-4" />}
          label="Fleet Status"
          value={`${activeAgents.length} active`}
          sub={`${agents.length} total · ${sandboxes.length} sandbox${sandboxes.length !== 1 ? 'es' : ''}`}
          accent={activeAgents.length > 0 ? 'success' : 'muted'}
        />
      </div>

      {/* ── Two-column: Agents + Sandboxes ────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Agent Fleet */}
        <section aria-labelledby="fleet-heading">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-[var(--text-muted)]" aria-hidden="true" />
              <h2 id="fleet-heading" className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wide">
                Agent Fleet ({agents.length})
              </h2>
            </div>
            <button
              type="button"
              onClick={() => navigate(`/project/${projectId}/agents`)}
              className="flex items-center gap-1 text-xs text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] font-medium transition-colors"
            >
              Manage
              <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          {agents.length === 0 ? (
            <EmptyState icon={Bot} message="No agents yet. Go to the Agents page to create one." />
          ) : (
            <div className="space-y-2">
              {agents.map(agent => {
                const st = statusMap.get(agent.id);
                const roleColor = ROLE_COLORS[agent.role] ?? '#64748b';
                const statusColor = STATUS_COLORS[agent.status] ?? '#64748b';
                const queueSize = st?.queue_size ?? 0;

                return (
                  <div
                    key={agent.id}
                    className="flex items-center gap-3 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3.5 py-2.5 hover:border-[var(--border-color-hover)] transition-colors cursor-pointer"
                    onClick={() => navigate(`/project/${projectId}/agents`)}
                  >
                    <div
                      className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                      style={{ backgroundColor: roleColor }}
                    >
                      {agent.display_name.charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-[var(--text-primary)] truncate">{agent.display_name}</span>
                        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }} />
                        {agent.thinking_enabled && <BrainCircuit className="w-3 h-3 text-[var(--color-accent)] shrink-0" />}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
                        <span className="capitalize">{agent.role}</span>
                        <span className="text-[var(--text-faint)]">·</span>
                        <Cpu className="w-2.5 h-2.5" />
                        <span className="font-mono truncate">{agent.model}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] shrink-0">
                      {queueSize > 0 && (
                        <span className="text-[var(--color-warning)] font-medium">{queueSize} queued</span>
                      )}
                      {sandboxes.some(sb => sb.agent_id === agent.id) && (
                        <span className="text-[var(--color-success)] flex items-center gap-1">
                          <Monitor className="w-3 h-3" /> sandbox
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Sandbox Previews */}
        <section aria-labelledby="sandbox-heading">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Monitor className="w-4 h-4 text-[var(--text-muted)]" aria-hidden="true" />
              <h2 id="sandbox-heading" className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wide">
                Sandboxes ({sandboxes.length})
              </h2>
            </div>
            <button
              type="button"
              onClick={() => navigate(`/project/${projectId}/sandbox`)}
              className="flex items-center gap-1 text-xs text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] font-medium transition-colors"
            >
              Open Sandbox
              <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          {sandboxes.length === 0 ? (
            <EmptyState icon={Monitor} message="No sandboxes running. Agents with sandbox access will appear here." />
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {sandboxes.slice(0, 4).map(sb => (
                <SandboxThumbnail
                  key={sb.id}
                  sandbox={sb}
                  agents={agents}
                  onClick={() => navigate(`/project/${projectId}/sandbox`)}
                />
              ))}
              {sandboxes.length > 4 && (
                <button
                  type="button"
                  onClick={() => navigate(`/project/${projectId}/sandbox`)}
                  className="col-span-2 text-center text-xs text-[var(--color-primary)] hover:underline py-2"
                >
                  +{sandboxes.length - 4} more sandbox{sandboxes.length - 4 !== 1 ? 'es' : ''}
                </button>
              )}
            </div>
          )}
        </section>
      </div>

      {/* ── Recent Activity (compact) ─────────────────────────────── */}
      <section aria-labelledby="activity-heading">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[var(--text-muted)]" aria-hidden="true" />
            <h2 id="activity-heading" className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wide">
              Recent LLM Calls
            </h2>
          </div>
        </div>

        {usage?.recent_calls && usage.recent_calls.length > 0 ? (
          <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] overflow-hidden">
            <div className="grid grid-cols-[1fr_100px_100px_80px_80px] gap-2 px-4 py-2 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider border-b border-[var(--border-color-subtle)] bg-[var(--surface-muted)]">
              <span>Model</span>
              <span>Input Tokens</span>
              <span>Output Tokens</span>
              <span>Cost</span>
              <span>Time</span>
            </div>
            {usage.recent_calls.slice(0, 8).map((call, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_100px_100px_80px_80px] gap-2 px-4 py-2 items-center border-b border-[var(--border-color-subtle)] last:border-b-0 text-sm"
              >
                <span className="font-mono text-xs text-[var(--text-secondary)] truncate">{call.model}</span>
                <span className="text-xs text-[var(--text-muted)]">{formatNumber(call.input_tokens)}</span>
                <span className="text-xs text-[var(--text-muted)]">{formatNumber(call.output_tokens)}</span>
                <span className="text-xs font-medium text-[var(--text-primary)]">${call.estimated_cost_usd.toFixed(4)}</span>
                <span className="text-[11px] text-[var(--text-faint)]">
                  <Clock className="w-3 h-3 inline mr-0.5" />
                  {formatTimeAgo(call.created_at)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={Activity} message="No LLM calls recorded yet." />
        )}
      </section>
    </div>
  );
}

// ── Stat Card ──────────────────────────────────────────────────────────────

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  accent: 'primary' | 'success' | 'warning' | 'danger' | 'muted';
  progress?: number;
}

function StatCard({ icon, label, value, sub, accent, progress }: StatCardProps) {
  const accentVar = accent === 'muted' ? 'var(--text-muted)' : `var(--color-${accent})`;

  return (
    <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className="text-[var(--text-muted)]">{icon}</div>
        <span className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-lg font-bold" style={{ color: accentVar }}>{value}</div>
      <div className="text-[11px] text-[var(--text-faint)] mt-0.5">{sub}</div>
      {progress !== undefined && (
        <div className="mt-2 h-1.5 rounded-full bg-[var(--surface-muted)] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${progress}%`, backgroundColor: accentVar }}
          />
        </div>
      )}
    </div>
  );
}

// ── Sandbox Thumbnail ──────────────────────────────────────────────────────

function SandboxThumbnail({ sandbox, agents, onClick }: { sandbox: Sandbox; agents: Agent[]; onClick: () => void }) {
  const { frameUrl, isConnected } = useScreenStream(sandbox.orchestrator_sandbox_id);
  const agentRole = sandbox.agent_id ? agents.find(a => a.id === sandbox.agent_id)?.role : undefined;
  const roleColor = ROLE_COLORS[agentRole ?? 'engineer'] ?? '#64748b';

  return (
    <button
      type="button"
      onClick={onClick}
      className="relative rounded-lg border border-[var(--border-color)] overflow-hidden aspect-video hover:border-[var(--color-primary)]/50 transition-all group"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)' }}
    >
      {frameUrl ? (
        <img src={frameUrl} alt={`${sandbox.agent_name ?? 'Unknown'} sandbox`} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center gap-1.5">
          <Monitor className="w-6 h-6 text-slate-500" />
          <span className="text-[9px] text-slate-500 font-medium">
            {isConnected ? 'Waiting for display…' : 'Connecting…'}
          </span>
        </div>
      )}

      {/* Overlay */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded flex items-center justify-center text-[8px] font-bold text-white" style={{ backgroundColor: roleColor }}>
            {(sandbox.agent_name ?? 'U').charAt(0).toUpperCase()}
          </div>
          <span className="text-[11px] font-medium text-white truncate">{sandbox.agent_name ?? 'Unknown'}</span>
          <div className={`w-1.5 h-1.5 rounded-full ml-auto shrink-0 ${isConnected ? 'bg-green-400' : 'bg-gray-500'}`} />
        </div>
      </div>
    </button>
  );
}

// ── Empty State ────────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, message }: { icon: React.ComponentType<{ className?: string }>; message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--surface-muted)] p-8 text-center">
      <Icon className="w-8 h-8 mx-auto text-[var(--text-faint)] mb-2" />
      <p className="text-sm text-[var(--text-muted)]">{message}</p>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default DashboardPage;
