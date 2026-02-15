import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatView } from './ChatView';

const useChatMock = vi.fn();

vi.mock('../../hooks', () => ({
  useChat: (...args: unknown[]) => useChatMock(...args),
}));

describe('ChatView', () => {
  it('shows waking up status while waiting for GM reply', () => {
    useChatMock.mockReturnValue({
      messages: [],
      isLoading: false,
      isSending: true,
      gmStatus: 'busy',
      isAwaitingGmReply: true,
      error: null,
      sendMessage: vi.fn(),
    });

    render(<ChatView projectId="project-1" />);

    expect(screen.getByText('Waking up...')).toBeInTheDocument();
    expect(screen.getByText('GM is waking up and processing your request.')).toBeInTheDocument();
  });

  it('shows processing status after GM has started replying', () => {
    useChatMock.mockReturnValue({
      messages: [],
      isLoading: false,
      isSending: true,
      gmStatus: 'busy',
      isAwaitingGmReply: false,
      error: null,
      sendMessage: vi.fn(),
    });

    render(<ChatView projectId="project-1" />);

    expect(screen.getByText('Processing...')).toBeInTheDocument();
  });
});
