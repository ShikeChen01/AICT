import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAgents } from '../../hooks';
import { useOptionalAgentStreamContext } from '../../contexts/AgentStreamContext';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { AgentLogData } from '../../types';
import { Badge, Button } from '../ui';
import { stopAgent, deleteAgent } from '../../api/client';

interface AgentsPanelProps {
  projectId: string;
  selectedAgentId?: string | null;
  onSelectAgent?: (agentId: string) => void;
}

function statusDotClass(statusLabel: string): string {
  if (statusLabel === 'sleeping') return 'bg-[var(--text-faint)]';
  if (statusLabel === 'busy') return 'bg-[var(--color-warning)] animate-pulse';
  if (statusLabel === 'waiting') return 'bg-[var(--color-warning)] animate-pulse';
  if (statusLabel === 'idle') return 'bg-[var(--color-primary)]';
  return 'bg-[var(--color-success)]';
}

export function AgentsPanel({ projectId, selectedAgentId, onSelectAgent }: AgentsPanelProps) {
  const { agents, isLoading, error, refreshAgents } = useAgents(projectId);
  const { subscribe } = useWebSocket(projectId);
  const streamContext = useOptionalAgentStreamContext();
  const getBuffer = streamContext?.getBuffer;
  const [agentBuffers, setAgentBuffers] = useState<Record<string, string[]>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [stopToast, setStopToast] = useState<string | null>(null);

  const rows = useMemo(() => {
    return agents.map((agent) => {
      const statusLabel =
        agent.status === 'active' && agent.queue_size === 0
          ? 'idle'
          : agent.status;
      return { ...agent, statusLabel };
    });
  }, [agents]);

  const effectiveExpandedId = selectedAgentId ?? expandedId;

  const handleStop = useCallback(async (agentId: string, displayName: string) => {
    setStoppingIds((prev) => new Set(prev).add(agentId));
    try {
      await stopAgent(agentId);
      setStopToast(`Agent "${displayName}" stopped.`);
      setTimeout(() => setStopToast(null), 3000);
      void refreshAgents();
    } catch {
      setStopToast(`Failed to stop "${displayName}".`);
      setTimeout(() => setStopToast(null), 3000);
    } finally {
      setStoppingIds((prev) => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  }, [refreshAgents]);

  const handleStopAll = useCallback(async () => {
    if (rows.length === 0) return;
    setStoppingIds(new Set(rows.map((a) => a.id)));
    await Promise.allSettled(rows.map((a) => stopAgent(a.id)));
    setStopToast('All agents stopped.');
    setTimeout(() => setStopToast(null), 3000);
    setStoppingIds(new Set());
    void refreshAgents();
  }, [rows, refreshAgents]);

  const handleDelete = useCallback(async (agentId: string, displayName: string) => {
    if (!window.confirm(`Remove agent "${displayName}"? This cannot be undone.`)) return;
    setDeletingIds((prev) => new Set(prev).add(agentId));
    try {
      await deleteAgent(agentId);
      setStopToast(`Agent "${displayName}" removed.`);
      setTimeout(() => setStopToast(null), 3000);
      void refreshAgents();
    } catch {
      setStopToast(`Failed to remove "${displayName}".`);
      setTimeout(() => setStopToast(null), 3000);
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  }, [refreshAgents]);

  // Refresh agent list when the server broadcasts agent_stopped
  useEffect(() => {
    const unsub = subscribe('agent_stopped', () => {
      void refreshAgents();
    });
    return unsub;
  }, [subscribe, refreshAgents]);

  useEffect(() => {
    if (streamContext) return;
    const pushLine = (agentId: string, line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      setAgentBuffers((prev) => {
        const current = prev[agentId] ?? [];
        const next = [...current, trimmed].slice(-20);
        return { ...prev, [agentId]: next };
      });
    };
    const unsubscribeAgentLog = subscribe<AgentLogData>('agent_log', (data) => {
      let prefix: string = data.log_type;
      if (data.log_type === 'tool_call') prefix = `tool:${data.tool_name || 'call'}`;
      if (data.log_type === 'tool_result') prefix = `result:${data.tool_name || 'tool'}`;
      pushLine(data.agent_id, `[${prefix}] ${data.content}`);
    });
    return () => {
      unsubscribeAgentLog();
    };
  }, [streamContext, subscribe]);

  return (
    <aside className="h-full min-h-0 w-full min-w-0 bg-transparent flex flex-col overflow-hidden">
      {rows.length > 0 && (
        <div className="flex items-center justify-end px-2 pt-2">
          <button
            type="button"
            title="Stop all agents"
            disabled={stoppingIds.size > 0}
            onClick={handleStopAll}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-[var(--color-danger)] border border-[var(--color-danger)]/40 hover:bg-[var(--color-danger-light)] disabled:opacity-40 transition-colors"
          >
            <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
              <rect x="2" y="2" width="8" height="8" rx="1" />
            </svg>
            Stop All
          </button>
        </div>
      )}
      {stopToast && (
        <div className="m-2 rounded-lg border border-[var(--border-color)] bg-gray-800 px-3 py-2 text-xs text-white shadow-lg">
          {stopToast}
        </div>
      )}
      {error && (
        <div className="m-2 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger-light)] px-3 py-2 text-xs text-[var(--color-danger)]">
          {error.message}
        </div>
      )}

      {isLoading && rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-muted)]">
          Loading agents...
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-2 space-y-2">
          {rows.map((agent) => (
            <section
              key={agent.id}
              className={`rounded-lg border p-3 ${
                agent.id === effectiveExpandedId
                  ? 'border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5'
                  : 'border-[var(--border-color)] bg-[var(--surface-card)]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setExpandedId((prev) => (prev === agent.id ? null : agent.id));
                    onSelectAgent?.(agent.id);
                  }}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${statusDotClass(agent.statusLabel)}`}
                    aria-hidden
                  />
                  <p className="truncate text-sm font-medium text-[var(--text-primary)]">{agent.display_name}</p>
                  <Badge
                    variant={agent.role === 'manager' ? 'manager' : agent.role === 'cto' ? 'cto' : 'engineer'}
                  >
                    {agent.role}
                  </Badge>
                </button>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-[var(--text-muted)] uppercase">{agent.statusLabel}</span>
                  <button
                    type="button"
                    title={`Stop ${agent.display_name}`}
                    disabled={stoppingIds.has(agent.id)}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStop(agent.id, agent.display_name);
                    }}
                    className="flex items-center justify-center w-5 h-5 rounded text-[var(--color-danger)] hover:bg-[var(--color-danger-light)] hover:text-[var(--color-danger)] disabled:opacity-40 transition-colors"
                  >
                    {stoppingIds.has(agent.id) ? (
                      <span className="w-2.5 h-2.5 border border-[var(--color-danger)]/40 border-t-transparent rounded-full animate-spin block" />
                    ) : (
                      <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
                        <rect x="2" y="2" width="8" height="8" rx="1" />
                      </svg>
                    )}
                  </button>
                  {agent.role !== 'manager' && agent.role !== 'cto' && (
                    <button
                      type="button"
                      title={`Remove ${agent.display_name}`}
                      disabled={deletingIds.has(agent.id)}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(agent.id, agent.display_name);
                      }}
                      className="flex items-center justify-center w-5 h-5 rounded text-[var(--text-faint)] hover:bg-[var(--color-danger-light)] hover:text-[var(--color-danger)] disabled:opacity-40 transition-colors"
                    >
                      {deletingIds.has(agent.id) ? (
                        <span className="w-2.5 h-2.5 border border-[var(--text-faint)] border-t-transparent rounded-full animate-spin block" />
                      ) : (
                        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <line x1="3" y1="3" x2="9" y2="9" />
                          <line x1="9" y1="3" x2="3" y2="9" />
                        </svg>
                      )}
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-2 flex items-center gap-3 text-xs text-[var(--text-muted)]">
                <span>Queue: {agent.queue_size}</span>
                <span>Pending messages: {agent.pending_message_count ?? 0}</span>
              </div>

              <div className="mt-2">
                <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">Latest activity</p>
                <div className="mt-1 rounded border border-[var(--border-color)] bg-[var(--surface-muted)] px-2 py-1 text-[11px] text-[var(--text-secondary)] leading-4 max-h-32 overflow-y-auto">
                  {(getBuffer?.(agent.id)?.chunks.length ?? 0) > 0 ? (
                    <ul className="space-y-1">
                      {(getBuffer?.(agent.id)?.chunks ?? [])
                        .slice(-10)
                        .reverse()
                        .map((chunk, idx) => (
                          <li key={`${agent.id}-buffer-${idx}`} className="truncate">
                            {chunk.type === 'text' || chunk.type === 'message'
                              ? chunk.content
                              : `${chunk.toolName} ${chunk.type === 'tool_result' ? (chunk.success ? 'OK' : 'Error') : 'call'}`}
                          </li>
                        ))}
                    </ul>
                  ) : (agentBuffers[agent.id] ?? []).length > 0 ? (
                    <ul className="space-y-1">
                      {(agentBuffers[agent.id] ?? [])
                        .slice(-10)
                        .reverse()
                        .map((line, idx) => (
                          <li key={`${agent.id}-fallback-buffer-${idx}`} className="truncate">
                            {line}
                          </li>
                        ))}
                    </ul>
                  ) : (
                    <p className="text-[var(--text-faint)]">No recent activity.</p>
                  )}
                </div>
              </div>

              {effectiveExpandedId === agent.id && agent.task_queue.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {agent.task_queue.map((task) => (
                    <li key={task.id} className="rounded border border-[var(--border-color)] bg-[var(--surface-muted)] px-2 py-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-medium text-[var(--text-primary)]">{task.title}</p>
                        <span className="text-[10px] uppercase text-[var(--text-muted)]">{task.status}</span>
                      </div>
                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        C{task.critical} / U{task.urgent}
                        {task.module_path ? ` · ${task.module_path}` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : effectiveExpandedId === agent.id ? (
                <p className="mt-3 text-xs text-[var(--text-faint)]">No queued tasks.</p>
              ) : (
                <div className="mt-3">
                  <Button size="sm" variant="ghost" onClick={() => setExpandedId(agent.id)}>
                    Show queue
                  </Button>
                </div>
              )}
            </section>
          ))}

          {rows.length === 0 && (
            <div className="text-sm text-[var(--text-muted)] text-center py-8">No agents in this project.</div>
          )}
        </div>
      )}
    </aside>
  );
}

export default AgentsPanel;

