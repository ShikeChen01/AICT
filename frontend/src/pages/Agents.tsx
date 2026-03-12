/**
 * Agents Page — Unified agent management with sidebar hierarchy.
 *
 * Left sidebar: agent tree grouped by role (Manager → CTO → Engineers).
 * Right panel: tabbed detail view (Prompt Builder, Templates, Overview).
 *
 * Replaces the old Agent Build page with a more cohesive experience.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  Bot,
  BrainCircuit,
  Cpu,
  Users,
  Blocks,
  Wrench,
  Trash2,
  StopCircle,
  Zap,
  MonitorSmartphone,
} from 'lucide-react';
import {
  getProject,
  getAgents,
  getAgentStatuses,
  getProjectUsage,
  stopAgent,
  deleteAgent,
  wakeAgent,
} from '../api/client';
import type { Project, Agent, AgentStatusWithQueue, ProjectUsageResponse } from '../types';
import { AppLayout } from '../components/Layout';
import { PromptBuilderPage } from '../components/PromptBuilder';
import { AgentTemplatesSection } from '../components/Agents/AgentTemplatesSection';

// ── Constants ──────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  manager: '#f59e0b',
  cto: '#8b5cf6',
  engineer: '#3b82f6',
};

const ROLE_ORDER: Record<string, number> = { manager: 0, cto: 1, engineer: 2 };

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  busy: '#f59e0b',
  sleeping: '#64748b',
};

type Tab = 'builder' | 'templates' | 'overview';

// ── Page Shell ─────────────────────────────────────────────────────────────

export function AgentsPage() {
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
      <AgentsContent projectId={projectId} />
    </AppLayout>
  );
}

// ── Agents Content ─────────────────────────────────────────────────────────

function AgentsContent({ projectId }: { projectId: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [statuses, setStatuses] = useState<AgentStatusWithQueue[]>([]);
  const [usage, setUsage] = useState<ProjectUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('builder');

  const fetchData = useCallback(async () => {
    try {
      const [agentList, statusList, usageData] = await Promise.all([
        getAgents(projectId),
        getAgentStatuses(projectId).catch(() => [] as AgentStatusWithQueue[]),
        getProjectUsage(projectId).catch(() => null),
      ]);
      setAgents(agentList);
      setStatuses(statusList);
      setUsage(usageData);

      // Auto-select first agent if nothing selected
      if (!selectedAgentId && agentList.length > 0) {
        setSelectedAgentId(agentList[0].id);
      }
    } catch {
      // Silently fail on refresh — data will be stale
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedAgentId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 20000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const sortedAgents = useMemo(
    () => [...agents].sort((a, b) => (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9)),
    [agents],
  );

  const statusMap = useMemo(
    () => new Map(statuses.map(s => [s.id, s])),
    [statuses],
  );

  const selectedAgent = agents.find(a => a.id === selectedAgentId) ?? null;

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-primary)]" />
      </div>
    );
  }

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'builder', label: 'Prompt Builder', icon: <Blocks className="w-3.5 h-3.5" /> },
    { id: 'templates', label: 'Templates', icon: <Users className="w-3.5 h-3.5" /> },
    { id: 'overview', label: 'Overview', icon: <Bot className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* ── Left Sidebar: Agent Hierarchy ─────────────────────── */}
      <aside className="w-64 shrink-0 border-r border-[var(--border-color)] bg-[var(--surface-card)] flex flex-col min-h-0">
        <div className="px-3 py-3 border-b border-[var(--border-color)]">
          <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Agent Hierarchy</h2>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {sortedAgents.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <Bot className="w-6 h-6 mx-auto text-[var(--text-faint)] mb-2" />
              <p className="text-xs text-[var(--text-muted)]">No agents yet</p>
            </div>
          ) : (
            <AgentTree
              agents={sortedAgents}
              selectedId={selectedAgentId}
              onSelect={(id) => { setSelectedAgentId(id); setActiveTab('builder'); }}
              onStop={(id) => stopAgent(id).then(fetchData)}
              onWake={(id) => wakeAgent(id).then(fetchData)}
              onDelete={(id) => deleteAgent(id).then(fetchData)}
            />
          )}
        </div>
      </aside>

      {/* ── Right Panel ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0 bg-[var(--app-bg)]">
        {/* Tab bar */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-[var(--border-color)] bg-[var(--surface-card)]">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                ${activeTab === t.id
                  ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
                }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {activeTab === 'builder' && (
            <PromptBuilderPage projectId={projectId} />
          )}
          {activeTab === 'templates' && (
            <div className="h-full overflow-y-auto p-6">
              <AgentTemplatesSection projectId={projectId} />
            </div>
          )}
          {activeTab === 'overview' && selectedAgent && (
            <AgentOverview agent={selectedAgent} status={statusMap.get(selectedAgent.id) ?? null} usage={usage} />
          )}
          {activeTab === 'overview' && !selectedAgent && (
            <div className="flex items-center justify-center h-full text-sm text-[var(--text-muted)]">
              Select an agent from the sidebar to view details.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Agent Tree ─────────────────────────────────────────────────────────────

interface AgentTreeProps {
  agents: Agent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onStop: (id: string) => void;
  onWake: (id: string) => void;
  onDelete: (id: string) => void;
}

function AgentTree({ agents, selectedId, onSelect, onStop, onWake, onDelete }: AgentTreeProps) {
  // Group by role
  const groups: { role: string; agents: Agent[] }[] = [];
  let currentRole = '';
  for (const a of agents) {
    if (a.role !== currentRole) {
      currentRole = a.role;
      groups.push({ role: a.role, agents: [] });
    }
    groups[groups.length - 1].agents.push(a);
  }

  return (
    <div className="space-y-1">
      {groups.map(g => (
        <div key={g.role}>
          <div className="px-3 py-1 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">
            {g.role}s
          </div>
          {g.agents.map((agent) => {
            const isSelected = agent.id === selectedId;
            const roleColor = ROLE_COLORS[agent.role] ?? '#64748b';
            const statusColor = STATUS_COLORS[agent.status] ?? '#64748b';
            const indent = agent.role === 'manager' ? 0 : agent.role === 'cto' ? 1 : 2;

            return (
              <div key={agent.id} style={{ paddingLeft: `${indent * 12 + 8}px` }}>
                <button
                  type="button"
                  onClick={() => onSelect(agent.id)}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors group
                    ${isSelected
                      ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]'
                    }`}
                >
                  {/* Connector line for hierarchy visual */}
                  {indent > 0 && (
                    <div className="w-3 border-l border-b border-[var(--border-color)] h-3 shrink-0 -ml-1 mb-1" />
                  )}
                  <div
                    className="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold text-white shrink-0"
                    style={{ backgroundColor: roleColor }}
                  >
                    {agent.display_name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-xs font-medium truncate flex-1">{agent.display_name}</span>
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }} />

                  {/* Hover actions */}
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                    {agent.status === 'sleeping' ? (
                      <button
                        onClick={e => { e.stopPropagation(); onWake(agent.id); }}
                        className="p-0.5 text-[var(--text-faint)] hover:text-[var(--color-success)]"
                        title="Wake"
                      >
                        <Zap className="w-3 h-3" />
                      </button>
                    ) : (
                      <button
                        onClick={e => { e.stopPropagation(); onStop(agent.id); }}
                        className="p-0.5 text-[var(--text-faint)] hover:text-[var(--color-danger)]"
                        title="Stop"
                      >
                        <StopCircle className="w-3 h-3" />
                      </button>
                    )}
                    {agent.role === 'engineer' && (
                      <button
                        onClick={e => { e.stopPropagation(); onDelete(agent.id); }}
                        className="p-0.5 text-[var(--text-faint)] hover:text-[var(--color-danger)]"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </button>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ── Agent Overview Tab ─────────────────────────────────────────────────────

interface AgentOverviewProps {
  agent: Agent;
  status: AgentStatusWithQueue | null;
  usage: ProjectUsageResponse | null;
}

function AgentOverview({ agent, status }: AgentOverviewProps) {
  const roleColor = ROLE_COLORS[agent.role] ?? '#64748b';
  const statusColor = STATUS_COLORS[agent.status] ?? '#64748b';

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Agent header */}
        <div className="flex items-center gap-4">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold text-white shrink-0"
            style={{ backgroundColor: roleColor }}
          >
            {agent.display_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 className="text-lg font-bold text-[var(--text-primary)]">{agent.display_name}</h2>
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <span className="capitalize">{agent.role}</span>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
              <span className="capitalize">{agent.status}</span>
              {agent.thinking_enabled && (
                <span className="flex items-center gap-1 text-[var(--color-accent)]">
                  <BrainCircuit className="w-3.5 h-3.5" /> Thinking
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-4">
          <InfoCard label="Model" value={agent.model} icon={<Cpu className="w-4 h-4" />} mono />
          <InfoCard label="Provider" value={agent.provider ?? 'Default'} icon={<Wrench className="w-4 h-4" />} />
          <InfoCard
            label="Queue"
            value={`${status?.queue_size ?? 0} tasks queued`}
            icon={<Zap className="w-4 h-4" />}
          />
          <InfoCard
            label="Sandbox"
            value={agent.sandbox_id ? `Active${agent.sandbox_persist ? ' (persistent)' : ''}` : 'None'}
            icon={<MonitorSmartphone className="w-4 h-4" />}
          />
        </div>

        {/* Memory / notes */}
        {agent.memory && (
          <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] p-4">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">Agent Memory</h3>
            <pre className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap font-mono max-h-60 overflow-y-auto">
              {typeof agent.memory === 'string' ? agent.memory : JSON.stringify(agent.memory, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Info Card ──────────────────────────────────────────────────────────────

function InfoCard({ label, value, icon, mono }: { label: string; value: string; icon: React.ReactNode; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] p-3">
      <div className="flex items-center gap-1.5 text-[var(--text-muted)] mb-1">
        {icon}
        <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <span className={`text-sm text-[var(--text-primary)] ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

export default AgentsPage;
