/**
 * useAgents Hook
 * Manages agent status + task queue state.
 */

import { useCallback, useEffect, useState } from 'react';
import type { AgentStatusWithQueue } from '../types';
import * as api from '../api/client';
import { useWebSocket } from './useWebSocket';

interface UseAgentsReturn {
  agents: AgentStatusWithQueue[];
  isLoading: boolean;
  error: Error | null;
  refreshAgents: () => Promise<void>;
  /** Optimistically update a single agent field without a full refresh. */
  patchAgent: (agentId: string, patch: Partial<AgentStatusWithQueue>) => void;
}

export function useAgents(projectId: string | null): UseAgentsReturn {
  const [agents, setAgents] = useState<AgentStatusWithQueue[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { subscribe } = useWebSocket(projectId);

  const refreshAgents = useCallback(async () => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);
    try {
      const [statusAgents, baseAgents] = await Promise.all([
        api.getAgentStatuses(projectId).catch(() => [] as AgentStatusWithQueue[]),
        api.getAgents(projectId).catch(() => []),
      ]);

      const byId = new Map<string, AgentStatusWithQueue>();
      for (const statusAgent of statusAgents) {
        byId.set(statusAgent.id, statusAgent);
      }

      for (const baseAgent of baseAgents) {
        if (!byId.has(baseAgent.id)) {
          byId.set(baseAgent.id, {
            ...baseAgent,
            queue_size: 0,
            pending_message_count: 0,
            task_queue: [],
          });
        }
      }

      const roleOrder: Record<string, number> = { manager: 0, cto: 1, engineer: 2 };
      const mergedAgents = Array.from(byId.values()).sort((a, b) => {
        const roleDiff = (roleOrder[a.role] ?? 99) - (roleOrder[b.role] ?? 99);
        if (roleDiff !== 0) return roleDiff;
        return a.display_name.localeCompare(b.display_name);
      });

      setAgents(mergedAgents);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch agents'));
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refreshAgents();
  }, [refreshAgents]);

  const patchAgent = useCallback((agentId: string, patch: Partial<AgentStatusWithQueue>) => {
    setAgents((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, ...patch } : a)),
    );
  }, []);

  useEffect(() => {
    if (!projectId) return;
    const interval = setInterval(() => {
      void refreshAgents();
    }, 20000);
    return () => clearInterval(interval);
  }, [projectId, refreshAgents]);

  useEffect(() => {
    if (!projectId) return;

    const unsubscribeAgent = subscribe('agent_status', () => {
      void refreshAgents();
    });
    const unsubscribeTaskCreated = subscribe('task_created', () => {
      void refreshAgents();
    });
    const unsubscribeTaskUpdated = subscribe('task_update', () => {
      void refreshAgents();
    });
    return () => {
      unsubscribeAgent();
      unsubscribeTaskCreated();
      unsubscribeTaskUpdated();
    };
  }, [projectId, refreshAgents, subscribe]);

  return {
    agents,
    isLoading,
    error,
    refreshAgents,
    patchAgent,
  };
}

export default useAgents;

