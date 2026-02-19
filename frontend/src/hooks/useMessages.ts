/**
 * useMessages — load conversation with selected agent, send message (POST messages/send).
 * Automatically marks incoming agent messages as read when the user views the conversation.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getMessages, sendMessage, markMessagesRead } from '../api/client';
import { useOptionalAgentStreamContext } from '../contexts/AgentStreamContext';
import type { ChannelMessage } from '../types';

const USER_AGENT_ID = '00000000-0000-0000-0000-000000000000';

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

function sortByCreatedAtAsc(list: ChannelMessage[]): ChannelMessage[] {
  return [...list].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

/**
 * Mark unread messages (status !== 'read') targeted at the user as read,
 * then update local state to reflect the new status.
 */
function markUnreadAsRead(
  messages: ChannelMessage[],
  setMessages: React.Dispatch<React.SetStateAction<ChannelMessage[]>>
): void {
  const unreadIds = messages
    .filter(
      (m) =>
        m.target_agent_id === USER_AGENT_ID &&
        m.status !== 'read'
    )
    .map((m) => m.id);
  if (unreadIds.length === 0) return;
  markMessagesRead(unreadIds).then(() => {
    setMessages((prev) =>
      prev.map((m) =>
        unreadIds.includes(m.id) ? { ...m, status: 'read' as const } : m
      )
    );
  }).catch(() => {
    // Silently ignore mark-read failures; messages will be retried on next load.
  });
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
      const sorted = sortByCreatedAtAsc(list);
      setMessages(sorted);
      // Mark messages as read when the user opens the conversation.
      markUnreadAsRead(sorted, setMessages);
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
        content: latestActivity.content,
        message_type: 'normal',
        status: 'received',
        broadcast: false,
        created_at: latestActivity.timestamp,
      };
      setMessages((prev) => {
        const updated = sortByCreatedAtAsc([...prev, incomingMessage]);
        // Mark newly received messages as read since the user is viewing the conversation.
        markUnreadAsRead([incomingMessage], setMessages);
        return updated;
      });
    }
  }, [projectId, agentId, streamContext]);

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
