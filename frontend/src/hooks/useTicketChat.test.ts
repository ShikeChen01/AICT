import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useTicketChat } from './useTicketChat';

const mockGetTicket = vi.fn();
const mockReplyToTicketAsUser = vi.fn();
const subscribeHandlers: Record<string, (data: unknown) => void> = {};

vi.mock('../api/client', () => ({
  getTicket: (...args: unknown[]) => mockGetTicket(...args),
  replyToTicketAsUser: (...args: unknown[]) => mockReplyToTicketAsUser(...args),
}));

vi.mock('./useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: (eventType: string, handler: (data: unknown) => void) => {
      subscribeHandlers[eventType] = handler;
      return () => {
        delete subscribeHandlers[eventType];
      };
    },
  }),
}));

describe('useTicketChat', () => {
  const ticketId = '55555555-5555-5555-5555-555555555555';
  const projectId = '00000000-0000-0000-0000-000000000001';

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTicket.mockResolvedValue({
      id: ticketId,
      project_id: projectId,
      from_agent_id: 'agent-1',
      to_agent_id: 'agent-2',
      header: 'Need help',
      ticket_type: 'question',
      status: 'open',
      messages: [
        { id: 'm1', ticket_id: ticketId, from_agent_id: 'agent-1', from_user_id: null, content: 'Question?', created_at: '2026-02-01T10:00:00Z' },
      ],
    });
  });

  it('fetches ticket and messages when ticketId is set', async () => {
    const { result } = renderHook(() => useTicketChat(ticketId, projectId));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockGetTicket).toHaveBeenCalledWith(ticketId);
    expect(result.current.ticket).not.toBeNull();
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe('Question?');
  });

  it('returns empty state when ticketId is null', () => {
    const { result } = renderHook(() => useTicketChat(null, projectId));

    expect(result.current.ticket).toBeNull();
    expect(result.current.messages).toEqual([]);
    expect(mockGetTicket).not.toHaveBeenCalled();
  });

  it('sendReply calls replyToTicketAsUser and refetches messages', async () => {
    mockGetTicket
      .mockResolvedValueOnce({
        id: ticketId,
        project_id: projectId,
        messages: [{ id: 'm1', content: 'Q', from_agent_id: 'a1', from_user_id: null, ticket_id: ticketId, created_at: '' }],
      })
      .mockResolvedValueOnce({
        id: ticketId,
        project_id: projectId,
        messages: [
          { id: 'm1', content: 'Q', from_agent_id: 'a1', from_user_id: null, ticket_id: ticketId, created_at: '' },
          { id: 'm2', content: 'Reply', from_agent_id: null, from_user_id: 'u1', ticket_id: ticketId, created_at: '' },
        ],
      });

    const { result } = renderHook(() => useTicketChat(ticketId, projectId));

    await waitFor(() => {
      expect(result.current.ticket).not.toBeNull();
    });

    mockReplyToTicketAsUser.mockResolvedValue(undefined);

    await act(async () => {
      await result.current.sendReply('Reply');
    });

    expect(mockReplyToTicketAsUser).toHaveBeenCalledWith(ticketId, 'Reply');
    expect(mockGetTicket).toHaveBeenCalledTimes(2);
  });
});
