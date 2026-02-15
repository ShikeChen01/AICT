import { useEffect, useMemo, useState } from 'react';
import { useAgents } from '../../hooks';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { AgentLogData, AgentStatusWithQueue, JobEventData } from '../../types';

interface AgentsPanelProps {
  projectId: string;
}

function roleBadgeClass(role: AgentStatusWithQueue['role']): string {
  if (role === 'gm') return 'bg-purple-100 text-purple-700';
  if (role === 'om') return 'bg-cyan-100 text-cyan-700';
  return 'bg-green-100 text-green-700';
}

function statusDotClass(statusLabel: string): string {
  if (statusLabel === 'sleeping') return 'bg-gray-400';
  if (statusLabel === 'busy') return 'bg-amber-500 animate-pulse';
  if (statusLabel === 'idle') return 'bg-blue-500';
  return 'bg-green-500';
}

export function AgentsPanel({ projectId }: AgentsPanelProps) {
  const { agents, isLoading, error } = useAgents(projectId);
  const { subscribe } = useWebSocket(projectId);
  const [agentBuffers, setAgentBuffers] = useState<Record<string, string[]>>({});

  const rows = useMemo(() => {
    return agents.map((agent) => {
      const statusLabel =
        agent.status === 'active' && agent.queue_size === 0 ? 'idle' : agent.status;
      return { ...agent, statusLabel };
    });
  }, [agents]);

  useEffect(() => {
    setAgentBuffers({});
  }, [projectId]);

  useEffect(() => {
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
      let prefix = data.log_type;
      if (data.log_type === 'tool_call') prefix = `tool:${data.tool_name || 'call'}`;
      if (data.log_type === 'tool_result') prefix = `result:${data.tool_name || 'tool'}`;
      pushLine(data.agent_id, `[${prefix}] ${data.content}`);
    });

    const unsubscribeJobStarted = subscribe<JobEventData>('job_started', (data) => {
      pushLine(data.agent_id, `[job] ${data.message || 'started'}`);
    });
    const unsubscribeJobProgress = subscribe<JobEventData>('job_progress', (data) => {
      const prefix = data.tool_name ? `[tool:${data.tool_name}]` : '[job]';
      pushLine(data.agent_id, `${prefix} ${data.message || 'in progress'}`);
    });
    const unsubscribeJobCompleted = subscribe<JobEventData>('job_completed', (data) => {
      pushLine(data.agent_id, `[done] ${data.result || 'completed'}`);
    });
    const unsubscribeJobFailed = subscribe<JobEventData>('job_failed', (data) => {
      pushLine(data.agent_id, `[error] ${data.error || 'failed'}`);
    });

    return () => {
      unsubscribeAgentLog();
      unsubscribeJobStarted();
      unsubscribeJobProgress();
      unsubscribeJobCompleted();
      unsubscribeJobFailed();
    };
  }, [subscribe]);

  return (
    <aside className="w-96 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-base font-semibold text-gray-900">Agents</h2>
        <p className="text-xs text-gray-500">Status and task queue</p>
      </div>

      {error && (
        <div className="m-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error.message}
        </div>
      )}

      {isLoading && rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
          Loading agents...
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {rows.map((agent) => (
            <section key={agent.id} className="rounded-lg border border-gray-200 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${statusDotClass(agent.statusLabel)}`}
                    aria-hidden
                  />
                  <p className="text-sm font-medium text-gray-900 truncate">{agent.display_name}</p>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase ${roleBadgeClass(agent.role)}`}
                  >
                    {agent.role}
                  </span>
                </div>
                <span className="text-[11px] text-gray-500 uppercase">{agent.statusLabel}</span>
              </div>

              <div className="mt-2 flex items-center gap-3 text-xs text-gray-600">
                <span>Queue: {agent.queue_size}</span>
                <span>Open tickets: {agent.open_ticket_count}</span>
              </div>

              <div className="mt-2">
                <p className="text-[10px] uppercase tracking-wide text-gray-500">Latest activity</p>
                <div className="mt-1 rounded border border-gray-100 bg-gray-50 px-2 py-1 text-[11px] text-gray-700 leading-4 overflow-hidden transition-all duration-200 max-h-10 hover:max-h-44">
                  {(agentBuffers[agent.id] ?? []).length > 0 ? (
                    <ul className="space-y-1">
                      {(agentBuffers[agent.id] ?? [])
                        .slice(-10)
                        .reverse()
                        .map((line, idx) => (
                          <li key={`${agent.id}-buffer-${idx}`} className="truncate">
                            {line}
                          </li>
                        ))}
                    </ul>
                  ) : (
                    <p className="text-gray-400">No recent activity.</p>
                  )}
                </div>
              </div>

              {agent.task_queue.length > 0 ? (
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
              ) : (
                <p className="mt-3 text-xs text-gray-400">No queued tasks.</p>
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

