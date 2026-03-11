/**
 * Dashboard Page — standalone top-nav page showing a live overview of all agents.
 *
 * Previously embedded as a tab inside AgentBuild; now promoted to its own route
 * for clearer information architecture and navigation.
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  Blocks,
  Bot,
  BrainCircuit,
  Cpu,
  ChevronRight,
  Play,
  Settings2,
  Plus,
  Layers,
} from 'lucide-react';
import {
  getProject,
  getAgents,
  listAgentBlocks,
  listTemplates,
  getAgentStatuses,
} from '../api/client';
import type { Project, Agent, PromptBlockConfig, AgentTemplate, AgentStatusWithQueue } from '../types';
import { AppLayout } from '../components/Layout';

// ── Types ──────────────────────────────────────────────────────────────────

interface AgentOverview {
  agent: Agent;
  blockCount: number;
  enabledBlockCount: number;
  customBlockCount: number;
  status: AgentStatusWithQueue | null;
}

// ── Role color mapping ─────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  manager: 'var(--color-manager, #f59e0b)',
  cto: 'var(--color-cto, #8b5cf6)',
  engineer: 'var(--color-engineer, #3b82f6)',
};

const STATUS_DOTS: Record<string, string> = {
  active: '#22c55e',
  busy: '#f59e0b',
  sleeping: '#64748b',
};

// ── Page Component ─────────────────────────────────────────────────────────

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
    } catch (_err) { // eslint-disable-line @typescript-eslint/no-unused-vars
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
            <button
              onClick={() => navigate('/projects')}
              className="mt-4 text-[var(--color-primary)] hover:underline"
            >
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
          <main className="max-w-5xl mx-auto px-6 py-6">
            <DashboardView
              projectId={projectId}
              onSwitchToBuilder={() => navigate(`/project/${projectId}/agent-build`)}
            />
          </main>
        </div>
      </div>
    </AppLayout>
  );
}

// ── Dashboard View ─────────────────────────────────────────────────────────

interface DashboardViewProps {
  projectId: string;
  onSwitchToBuilder: () => void;
}

function DashboardView({ projectId, onSwitchToBuilder }: DashboardViewProps) {
  const [agentOverviews, setAgentOverviews] = useState<AgentOverview[]>([]);
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const [agents, tmpls, statuses] = await Promise.all([
          getAgents(projectId),
          listTemplates(projectId),
          getAgentStatuses(projectId).catch(() => [] as AgentStatusWithQueue[]),
        ]);

        const blockResults = await Promise.allSettled(
          agents.map((a) => listAgentBlocks(a.id))
        );

        if (cancelled) return;

        const statusMap = new Map(statuses.map((s) => [s.id, s]));

        const overviews: AgentOverview[] = agents.map((agent, idx) => {
          const blocks: PromptBlockConfig[] =
            blockResults[idx].status === 'fulfilled' ? blockResults[idx].value : [];
          return {
            agent,
            blockCount: blocks.length,
            enabledBlockCount: blocks.filter((b) => b.enabled).length,
            customBlockCount: blocks.filter((b) => b.block_key.startsWith('custom_')).length,
            status: statusMap.get(agent.id) ?? null,
          };
        });

        setAgentOverviews(overviews);
        setTemplates(tmpls);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load dashboard');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="status">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-primary)]" aria-hidden="true" />
        <span className="ml-2 text-sm text-[var(--text-muted)]">Loading dashboard…</span>
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

  const systemTemplates = templates.filter((t) => t.is_system_default);
  const customTemplates = templates.filter((t) => !t.is_system_default);

  return (
    <div className="space-y-6">
      {/* Section: Agents overview */}
      <section aria-labelledby="agents-heading">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-[var(--text-muted)]" aria-hidden="true" />
            <h2 id="agents-heading" className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wide">
              Agents ({agentOverviews.length})
            </h2>
          </div>
          <button
            type="button"
            onClick={onSwitchToBuilder}
            className="flex items-center gap-1 text-xs text-[var(--color-primary)] hover:text-[var(--color-primary-hover)] font-medium transition-colors"
          >
            Open Builder
            <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>

        {agentOverviews.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--surface-muted)] p-8 text-center">
            <Bot className="w-8 h-8 mx-auto text-[var(--text-faint)] mb-2" aria-hidden="true" />
            <p className="text-sm text-[var(--text-muted)]">No agents yet. Switch to the Agent Builder to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3" role="list">
            {agentOverviews.map(({ agent, blockCount, enabledBlockCount, customBlockCount, status }) => {
              const roleColor = ROLE_COLORS[agent.role] ?? 'var(--text-muted)';
              const statusColor = STATUS_DOTS[agent.status] ?? '#64748b';
              const queueDepth = status?.queue_size ?? 0;

              return (
                <article
                  key={agent.id}
                  role="listitem"
                  className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] p-4 hover:border-[var(--border-color-hover)] transition-colors group"
                  aria-label={`Agent: ${agent.display_name}, role: ${agent.role}, status: ${agent.status}`}
                >
                  {/* Agent header row */}
                  <div className="flex items-center gap-2.5 mb-3">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white shrink-0"
                      style={{ backgroundColor: roleColor }}
                      aria-hidden="true"
                    >
                      {agent.display_name.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-[var(--text-primary)] truncate">
                          {agent.display_name}
                        </span>
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: statusColor }}
                          role="img"
                          aria-label={`Status: ${agent.status}`}
                        />
                      </div>
                      <span className="text-xs text-[var(--text-muted)] capitalize">{agent.role}</span>
                    </div>
                    {agent.thinking_enabled && (
                      <BrainCircuit className="w-4 h-4 text-[var(--color-accent)] shrink-0" aria-label="Thinking enabled" />
                    )}
                  </div>

                  {/* Model pill */}
                  <div className="flex items-center gap-1.5 mb-3">
                    <Cpu className="w-3 h-3 text-[var(--text-faint)]" aria-hidden="true" />
                    <span className="text-xs font-mono text-[var(--text-secondary)] truncate">{agent.model}</span>
                    {agent.provider && (
                      <span className="text-[10px] text-[var(--text-faint)] border border-[var(--border-color-subtle)] rounded px-1 py-px">
                        {agent.provider}
                      </span>
                    )}
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                    <div className="flex items-center gap-1" title="Prompt blocks (enabled / total)">
                      <Blocks className="w-3 h-3" aria-hidden="true" />
                      <span>
                        <span className="text-[var(--text-primary)] font-medium">{enabledBlockCount}</span>
                        /{blockCount} blocks
                      </span>
                    </div>
                    {customBlockCount > 0 && (
                      <div className="flex items-center gap-1" title="Custom blocks">
                        <Plus className="w-3 h-3" aria-hidden="true" />
                        <span>{customBlockCount} custom</span>
                      </div>
                    )}
                    {queueDepth > 0 && (
                      <div className="flex items-center gap-1 text-[var(--color-warning)]" title="Tasks in queue">
                        <Play className="w-3 h-3" aria-hidden="true" />
                        <span>{queueDepth} queued</span>
                      </div>
                    )}
                  </div>

                  {/* Sandbox indicator */}
                  {agent.sandbox_id && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-[var(--color-success)]">
                      <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
                      Sandbox active
                      {agent.sandbox_persist && <span className="text-[var(--text-faint)]">· persistent</span>}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* Section: Templates */}
      <section aria-labelledby="templates-heading">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-4 h-4 text-[var(--text-muted)]" aria-hidden="true" />
          <h2 id="templates-heading" className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wide">
            Agent Templates ({templates.length})
          </h2>
        </div>

        <div className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] overflow-hidden" role="table" aria-label="Agent templates">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_120px_140px_80px_80px] gap-2 px-4 py-2 text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider border-b border-[var(--border-color-subtle)] bg-[var(--surface-muted)]" role="row">
            <span role="columnheader">Template</span>
            <span role="columnheader">Role</span>
            <span role="columnheader">Model</span>
            <span role="columnheader">Thinking</span>
            <span role="columnheader">Type</span>
          </div>

          {systemTemplates.map((tmpl) => (
            <TemplateRow key={tmpl.id} template={tmpl} />
          ))}

          {systemTemplates.length > 0 && customTemplates.length > 0 && (
            <div className="border-t border-dashed border-[var(--border-color-subtle)]" role="separator" />
          )}

          {customTemplates.map((tmpl) => (
            <TemplateRow key={tmpl.id} template={tmpl} />
          ))}

          {templates.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-[var(--text-muted)]">
              No templates found.
            </div>
          )}
        </div>
      </section>

      {/* Quick action banner */}
      <button
        type="button"
        onClick={onSwitchToBuilder}
        className="w-full rounded-xl border border-[var(--color-primary)]/20 bg-[var(--color-primary)]/5 p-4 flex items-center gap-3 cursor-pointer hover:bg-[var(--color-primary)]/10 transition-colors text-left"
      >
        <div className="w-10 h-10 rounded-lg bg-[var(--color-primary)]/15 flex items-center justify-center shrink-0" aria-hidden="true">
          <Settings2 className="w-5 h-5 text-[var(--color-primary)]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Configure prompt blocks, models, and tools
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            Switch to the Agent Builder to edit system prompts, manage context budgets, and customize tool access per agent.
          </p>
        </div>
        <ChevronRight className="w-5 h-5 text-[var(--color-primary)] shrink-0" aria-hidden="true" />
      </button>
    </div>
  );
}

// ── TemplateRow ──────────────────────────────────────────────────────────────

function TemplateRow({ template }: { template: AgentTemplate }) {
  const roleColor = ROLE_COLORS[template.base_role] ?? 'var(--text-muted)';

  return (
    <div className="grid grid-cols-[1fr_120px_140px_80px_80px] gap-2 px-4 py-2.5 items-center border-b border-[var(--border-color-subtle)] last:border-b-0 hover:bg-[var(--surface-hover)] transition-colors text-sm" role="row">
      <div className="flex items-center gap-2 min-w-0" role="cell">
        <div
          className="w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: roleColor }}
          aria-hidden="true"
        />
        <span className="text-[var(--text-primary)] font-medium truncate">{template.name}</span>
      </div>
      <span className="text-xs text-[var(--text-muted)] capitalize" role="cell">{template.base_role}</span>
      <span className="text-xs font-mono text-[var(--text-secondary)] truncate" role="cell">{template.model}</span>
      <span role="cell">
        {template.thinking_enabled ? (
          <BrainCircuit className="w-3.5 h-3.5 text-[var(--color-accent)]" aria-label="Thinking enabled" />
        ) : (
          <span className="text-xs text-[var(--text-faint)]" aria-label="Thinking disabled">—</span>
        )}
      </span>
      <span role="cell">
        {template.is_system_default ? (
          <span className="text-[10px] font-medium text-[var(--color-primary)] bg-[var(--color-primary)]/10 rounded px-1.5 py-0.5">
            system
          </span>
        ) : (
          <span className="text-[10px] font-medium text-[var(--color-accent)] bg-[var(--color-accent)]/10 rounded px-1.5 py-0.5">
            custom
          </span>
        )}
      </span>
    </div>
  );
}

export default DashboardPage;
