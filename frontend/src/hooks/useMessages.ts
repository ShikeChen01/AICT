/**
 * useMessages — load conversation with selected agent, send message (POST messages/send).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getMessages, sendMessage } from '../api/client';
import { useOptionalAgentStreamContext } from '../contexts/AgentStreamContext';
import type { ChannelMessage } from '../types';
import { USER_AGENT_ID } from '../constants';

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
  send: (content: string, attachmentIds?: string[]) => Promise<ChannelMessage | null>;
  refresh: () => Promise<void>;
}

function sortByCreatedAtAsc(list: ChannelMessage[]): ChannelMessage[] {
  return [...list].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
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
  const streamContext = useOptionalAgentStreamContext();
  const lastSyncedActivityIdRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId || !agentId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await getMessages(projectId, agentId, limit, offset);
      setMessages(sortByCreatedAtAsc(list));
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

  useEffect(() => {
    if (!projectId || !agentId || !streamContext) return;
    const latestActivity = streamContext.activityLogs[streamContext.activityLogs.length - 1];
    if (!latestActivity) return;
    if (latestActivity.id === lastSyncedActivityIdRef.current) return;
    lastSyncedActivityIdRef.current = latestActivity.id;

    // Agent reply landed over websocket; append it directly to chatbox state.
    if (latestActivity.agent_id === agentId && latestActivity.log_type === 'message') {
      const incomingMessage: ChannelMessage = {
        id: latestActivity.id,
        project_id: latestActivity.project_id,
        from_agent_id: latestActivity.agent_id,
        target_agent_id: USER_AGENT_ID,
        from_user_id: null,
        content: latestActivity.content,
        message_type: 'normal',
        status: 'received',
        broadcast: false,
        created_at: latestActivity.timestamp,
        attachment_ids: [],
      };
      setMessages((prev) => sortByCreatedAtAsc([...prev, incomingMessage]));
    }
  }, [projectId, agentId, streamContext]);

  const send = useCallback(
    async (content: string, attachmentIds?: string[]): Promise<ChannelMessage | null> => {
      if (!projectId || !agentId) return null;
      const trimmed = content.trim();
      if (!trimmed && (!attachmentIds || attachmentIds.length === 0)) return null;
      setError(null);
      try {
        const msg = await sendMessage({
          project_id: projectId,
          target_agent_id: agentId,
          content: trimmed || ' ',
          ...(attachmentIds && attachmentIds.length > 0 ? { attachment_ids: attachmentIds } : {}),
        });
        setMessages((prev) => sortByCreatedAtAsc([...prev, msg]));
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
