import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TicketChat } from './TicketChat';

const mockGetTicket = vi.fn();
const mockReplyToTicketAsUser = vi.fn();

vi.mock('../../hooks/useTicketChat', () => ({
  useTicketChat: (ticketId: string, projectId: string) => {
    return {
      ticket: { id: ticketId, header: 'Need API key', ticket_type: 'question' },
      messages: [
        { id: 'm1', ticket_id: ticketId, from_agent_id: 'agent-1', from_user_id: null, content: 'What is the API key?', created_at: '2026-02-01T10:00:00Z' },
      ],
      isLoading: false,
      sendReply: mockReplyToTicketAsUser,
      closeTicket: vi.fn(),
    };
  },
}));

describe('TicketChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders header with agent name and task title', () => {
    render(
      <TicketChat
        ticketId="ticket-1"
        projectId="project-1"
        agentName="Engineer-1"
        taskTitle="Implement auth"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText(/Engineer-1/)).toBeInTheDocument();
    expect(screen.getByText(/Implement auth/)).toBeInTheDocument();
  });

  it('renders agent message', () => {
    render(
      <TicketChat
        ticketId="ticket-1"
        projectId="project-1"
        agentName="Engineer-1"
        taskTitle="Implement auth"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('What is the API key?')).toBeInTheDocument();
  });

  it('calls sendReply when user submits reply', async () => {
    mockReplyToTicketAsUser.mockResolvedValue(undefined);

    render(
      <TicketChat
        ticketId="ticket-1"
        projectId="project-1"
        agentName="Engineer-1"
        taskTitle="Implement auth"
        onClose={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/Type your reply/);
    fireEvent.change(input, { target: { value: 'Use env API_KEY' } });
    const sendButton = screen.getByRole('button', { name: /Send/i });
    fireEvent.click(sendButton);

    expect(mockReplyToTicketAsUser).toHaveBeenCalledWith('Use env API_KEY');
  });
});
