import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAgents } from '../../hooks';
import { useOptionalAgentStreamContext } from '../../contexts/AgentStreamContext';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { AgentLogData } from '../../types';
import { Badge, Button } from '../ui';
import { stopAgent } from '../../api/client';

interface AgentsPanelProps {
  projectId: string;
  selectedAgentId?: string | null;
  onSelectAgent?: (agentId: string) => void;
}

function statusDotClass(statusLabel: string): string {
  if (statusLabel === 'sleeping') return 'bg-gray-400';
  if (statusLabel === 'busy') return 'bg-amber-500 animate-pulse';
  if (statusLabel === 'waiting') return 'bg-orange-500 animate-pulse';
  if (statusLabel === 'idle') return 'bg-blue-500';
  return 'bg-green-500';
}

export function AgentsPanel({ projectId, selectedAgentId, onSelectAgent }: AgentsPanelProps) {
  const { agents, isLoading, error, refreshAgents } = useAgents(projectId);
  const { subscribe } = useWebSocket(projectId);
  const streamContext = useOptionalAgentStreamContext();
  const getBuffer = streamContext?.getBuffer;
  const [agentBuffers, setAgentBuffers] = useState<Record<string, string[]>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(new Set());
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
      {stopToast && (
        <div className="m-2 rounded-lg border border-gray-200 bg-gray-800 px-3 py-2 text-xs text-white shadow-lg">
          {stopToast}
        </div>
      )}
      {error && (
        <div className="m-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error.message}
        </div>
      )}

      {isLoading && rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
          Loading agents...
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-2 space-y-2">
          {rows.map((agent) => (
            <section
              key={agent.id}
              className={`rounded-lg border p-3 ${
                agent.id === effectiveExpandedId
                  ? 'border-[var(--color-primary)]/40 bg-blue-50/40'
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
                  <p className="truncate text-sm font-medium text-gray-900">{agent.display_name}</p>
                  <Badge
                    variant={agent.role === 'manager' ? 'manager' : agent.role === 'cto' ? 'cto' : 'engineer'}
                  >
                    {agent.role}
                  </Badge>
                </button>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-gray-500 uppercase">{agent.statusLabel}</span>
                  {agent.status === 'running' && (
                    <button
                      type="button"
                      title={`Stop ${agent.display_name}`}
                      disabled={stoppingIds.has(agent.id)}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStop(agent.id, agent.display_name);
                      }}
                      className="flex items-center justify-center w-5 h-5 rounded text-red-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-40 transition-colors"
                    >
                      {stoppingIds.has(agent.id) ? (
                        <span className="w-2.5 h-2.5 border border-red-400 border-t-transparent rounded-full animate-spin block" />
                      ) : (
                        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
                          <rect x="2" y="2" width="8" height="8" rx="1" />
                        </svg>
                      )}
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-2 flex items-center gap-3 text-xs text-gray-600">
                <span>Queue: {agent.queue_size}</span>
                <span>Pending messages: {agent.pending_message_count ?? 0}</span>
              </div>

              <div className="mt-2">
                <p className="text-[10px] uppercase tracking-wide text-gray-500">Latest activity</p>
                <div className="mt-1 rounded border border-gray-100 bg-gray-50 px-2 py-1 text-[11px] text-gray-700 leading-4 max-h-32 overflow-y-auto">
                  {(getBuffer?.(agent.id).chunks.length ?? 0) > 0 ? (
                    <ul className="space-y-1">
                      {(getBuffer?.(agent.id).chunks ?? [])
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
                    <p className="text-gray-400">No recent activity.</p>
                  )}
                </div>
              </div>

              {effectiveExpandedId === agent.id && agent.task_queue.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {agent.task_queue.map((task) => (
                    <li key={task.id} className="rounded border border-gray-100 bg-gray-50 px-2 py-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-medium text-gray-800">{task.title}</p>
                        <span className="text-[10px] uppercase text-gray-500">{task.status}</span>
                      </div>
                      <p className="mt-1 text-[11px] text-gray-500">
                        C{task.critical} / U{task.urgent}
                        {task.module_path ? ` · ${task.module_path}` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : effectiveExpandedId === agent.id ? (
                <p className="mt-3 text-xs text-gray-400">No queued tasks.</p>
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
            <div className="text-sm text-gray-500 text-center py-8">No agents in this project.</div>
          )}
        </div>
      )}
    </aside>
  );
}

export default AgentsPanel;

