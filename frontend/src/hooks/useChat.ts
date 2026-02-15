/**
 * useChat Hook
 * Manages chat state with real-time updates
 */

import { useState, useEffect, useCallback } from 'react';
import type { ChatMessage, ChatMessageCreate } from '../types';
import * as api from '../api/client';
import { useWebSocket } from './useWebSocket';

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  isSending: boolean;
  gmStatus: 'available' | 'busy';
  isAwaitingGmReply: boolean;
  error: Error | null;
  sendMessage: (content: string) => Promise<ChatMessage>;
  refreshMessages: () => Promise<void>;
}

export function useChat(projectId: string | null): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [gmStatus, setGmStatus] = useState<'available' | 'busy'>('available');
  const [isAwaitingGmReply, setIsAwaitingGmReply] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const { subscribe } = useWebSocket(projectId);

  // Fetch chat history
  const refreshMessages = useCallback(async () => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);

    try {
      const history = await api.getChatHistory(projectId);
      setMessages(history);
      if (history.some((msg) => msg.role === 'gm' || msg.role === 'manager')) {
        setIsAwaitingGmReply(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch chat history'));
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // Initial fetch
  useEffect(() => {
    refreshMessages();
  }, [refreshMessages]);

  // Subscribe to real-time updates
  useEffect(() => {
    if (!projectId) return;

    const unsubscribeMessage = subscribe<ChatMessage>('chat_message', (message) => {
      if (message.role === 'gm' || message.role === 'manager') {
        setIsAwaitingGmReply(false);
      }
      setMessages((prev) => {
        if (prev.some((msg) => msg.id === message.id)) {
          return prev;
        }
        return [...prev, message];
      });
    });

    const unsubscribeStatus = subscribe<{ status: 'available' | 'busy' }>(
      'gm_status',
      (data) => {
        setGmStatus(data.status);
      }
    );

    return () => {
      unsubscribeMessage();
      unsubscribeStatus();
    };
  }, [projectId, subscribe]);

  // Send message
  const sendMessage = useCallback(
    async (content: string): Promise<ChatMessage> => {
      if (!projectId) throw new Error('No project selected');

      const isFirstTurn = !messages.some((msg) => msg.role === 'gm' || msg.role === 'manager');
      setIsSending(true);
      setIsAwaitingGmReply(isFirstTurn);
      // Optimistic status while waiting for backend status events.
      setGmStatus('busy');
      setError(null);

      try {
        const messageData: ChatMessageCreate = { content };
        const response = await api.sendChatMessage(projectId, messageData);
        const gmMessage: ChatMessage = {
          id: response.id,
          project_id: response.project_id,
          role: response.role,
          content: response.content,
          attachments: response.attachments,
          created_at: response.created_at,
        };

        setMessages((prev) => {
          let next = prev;

          if (response.user_message && !next.some((m) => m.id === response.user_message!.id)) {
            next = [...next, response.user_message];
          }
          if (!next.some((m) => m.id === gmMessage.id)) {
            next = [...next, gmMessage];
          }

          return next;
        });

        return gmMessage;
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Failed to send message');
        setError(error);
        setIsAwaitingGmReply(false);
        throw error;
      } finally {
        setIsSending(false);
      }
    },
    [projectId, messages]
  );

  return {
    messages,
    isLoading,
    isSending,
    gmStatus,
    isAwaitingGmReply,
    error,
    sendMessage,
    refreshMessages,
  };
}

export default useChat;
