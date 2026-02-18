/**
 * useSessions — session history for inspector / session list.
 * Uses GET /api/v1/sessions (may 404 until Agent 2 lands).
 */

import { useCallback, useEffect, useState } from 'react';
import { getSessions } from '../api/client';
import type { AgentSession } from '../types';

interface UseSessionsOptions {
  projectId: string | null;
  agentId: string | null;
  limit?: number;
  offset?: number;
}

interface UseSessionsReturn {
  sessions: AgentSession[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useSessions({
  projectId,
  agentId,
  limit = 50,
  offset = 0,
}: UseSessionsOptions): UseSessionsReturn {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId || !agentId) {
      setSessions([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await getSessions(projectId, agentId, limit, offset);
      setSessions(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, agentId, limit, offset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    sessions,
    loading,
    error,
    refresh,
  };
}

export default useSessions;
