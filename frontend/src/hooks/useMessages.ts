/**
 * useMessages — load conversation with selected agent, send message (POST messages/send).
 */

import { useCallback, useEffect, useState } from 'react';
import { getMessages, sendMessage } from '../api/client';
import type { ChannelMessage } from '../types';

interface UseMessagesOptions {
  projectId: string | null;
  agentId: string | null;
  limit?: number;
  offset?: number;
}

interface UseMessagesReturn {
  messages: ChannelMessage[];
  loading: boolean;
  error: string | null;
  send: (content: string) => Promise<ChannelMessage | null>;
  refresh: () => Promise<void>;
}

export function useMessages({
  projectId,
  agentId,
  limit = 100,
  offset = 0,
}: UseMessagesOptions): UseMessagesReturn {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId || !agentId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await getMessages(projectId, agentId, limit, offset);
      setMessages(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load messages');
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, agentId, limit, offset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const send = useCallback(
    async (content: string): Promise<ChannelMessage | null> => {
      if (!projectId || !agentId || !content.trim()) return null;
      setError(null);
      try {
        const msg = await sendMessage({
          project_id: projectId,
          target_agent_id: agentId,
          content: content.trim(),
        });
        setMessages((prev) => [msg, ...prev]);
        return msg;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to send message');
        return null;
      }
    },
    [projectId, agentId]
  );

  return {
    messages,
    loading,
    error,
    send,
    refresh,
  };
}

export default useMessages;
