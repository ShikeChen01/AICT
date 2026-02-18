import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageList } from './MessageList';
import type { ChannelMessage } from '../../types';

const messages: ChannelMessage[] = [
  {
    id: '1',
    project_id: 'proj-1',
    from_agent_id: null,
    target_agent_id: 'agent-1',
    content: 'Hello from user',
    message_type: 'normal',
    status: 'sent',
    broadcast: false,
    created_at: '2026-02-01T10:00:00Z',
  },
  {
    id: '2',
    project_id: 'proj-1',
    from_agent_id: 'agent-1',
    target_agent_id: null,
    content: 'Hello from agent',
    message_type: 'normal',
    status: 'received',
    broadcast: false,
    created_at: '2026-02-01T10:01:00Z',
  },
];

describe('AgentChat MessageList', () => {
  it('renders messages', () => {
    render(<MessageList messages={messages} />);
    expect(screen.getByText('Hello from user')).toBeInTheDocument();
    expect(screen.getByText('Hello from agent')).toBeInTheDocument();
  });

  it('shows loading indicator when isLoading', () => {
    const { container } = render(<MessageList messages={[]} isLoading />);
    expect(container.querySelector('.animate-bounce')).toBeInTheDocument();
  });

  it('renders empty when no messages', () => {
    const { container } = render(<MessageList messages={[]} />);
    expect(container.querySelector('[class*="overflow-y-auto"]')).toBeInTheDocument();
  });
});
