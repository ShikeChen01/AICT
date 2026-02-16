/**
 * useTicketChat Hook
 * Manages state for a single ticket conversation (fetch, messages, send reply).
 */

import { useCallback, useEffect, useState } from 'react';
import type { Ticket, TicketMessage } from '../types';
import * as api from '../api/client';
import { useWebSocket } from './useWebSocket';

interface UseTicketChatReturn {
  ticket: Ticket | null;
  messages: TicketMessage[];
  isLoading: boolean;
  sendReply: (content: string) => Promise<void>;
  closeTicket: () => void;
}

export function useTicketChat(ticketId: string | null, projectId: string): UseTicketChatReturn {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<TicketMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { subscribe } = useWebSocket(projectId);

  useEffect(() => {
    if (!ticketId) return;
    setIsLoading(true);
    api.getTicket(ticketId).then((t) => {
      setTicket(t);
      setMessages(t.messages ?? []);
    }).finally(() => setIsLoading(false));
  }, [ticketId]);

  useEffect(() => {
    if (!ticketId) return;
    const unsub = subscribe('ticket_reply', (data: { ticket_id: string }) => {
      if (data.ticket_id === ticketId) {
        api.getTicket(ticketId).then((t) => setMessages(t.messages ?? []));
      }
    });
    return unsub;
  }, [ticketId, subscribe]);

  const sendReply = useCallback(async (content: string) => {
    if (!ticketId) return;
    await api.replyToTicketAsUser(ticketId, content);
    api.getTicket(ticketId).then((t) => setMessages(t.messages ?? []));
  }, [ticketId]);

  const closeTicket = useCallback(() => {}, []);

  return { ticket, messages, isLoading, sendReply, closeTicket };
}

export default useTicketChat;
