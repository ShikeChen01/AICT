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
      const nextAgents = await api.getAgentStatuses(projectId);
      setAgents(nextAgents);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch agents'));
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refreshAgents();
  }, [refreshAgents]);

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
  };
}

export default useAgents;

