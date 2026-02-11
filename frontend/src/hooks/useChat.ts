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
  error: Error | null;
  sendMessage: (content: string) => Promise<ChatMessage>;
  refreshMessages: () => Promise<void>;
}

export function useChat(projectId: string | null): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [gmStatus, setGmStatus] = useState<'available' | 'busy'>('available');
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
      setMessages((prev) => [...prev, message]);
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

      setIsSending(true);
      setError(null);

      // Optimistic update for user message
      const optimisticMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        project_id: projectId,
        role: 'user',
        content,
        attachments: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticMessage]);

      try {
        const messageData: ChatMessageCreate = { content };
        const response = await api.sendChatMessage(projectId, messageData);
        
        // Replace optimistic message and add GM response
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.id !== optimisticMessage.id);
          // The response might include both user message and GM response
          // or just the GM response - handle both cases
          return [...filtered, response];
        });

        return response;
      } catch (err) {
        // Remove optimistic message on error
        setMessages((prev) => prev.filter((m) => m.id !== optimisticMessage.id));
        const error = err instanceof Error ? err : new Error('Failed to send message');
        setError(error);
        throw error;
      } finally {
        setIsSending(false);
      }
    },
    [projectId]
  );

  return {
    messages,
    isLoading,
    isSending,
    gmStatus,
    error,
    sendMessage,
    refreshMessages,
  };
}

export default useChat;
