import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageList } from './MessageList';
import { mockChatMessages } from '../../test/mocks';

describe('MessageList', () => {
  it('should render empty state when no messages', () => {
    render(<MessageList messages={[]} />);
    
    expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    expect(screen.getByText('Send a message to the GM agent')).toBeInTheDocument();
  });

  it('should render all messages', () => {
    render(<MessageList messages={mockChatMessages} />);
    
    expect(screen.getByText(/Hello GM, can you help me/)).toBeInTheDocument();
    expect(screen.getByText(/Of course! I'd recommend/)).toBeInTheDocument();
  });

  it('should show user avatar for user messages', () => {
    render(<MessageList messages={mockChatMessages} />);
    
    // User avatar shows 'U'
    expect(screen.getByText('U')).toBeInTheDocument();
  });

  it('should show GM avatar for GM messages', () => {
    render(<MessageList messages={mockChatMessages} />);
    
    // GM avatar shows 'GM'
    expect(screen.getAllByText('GM').length).toBeGreaterThan(0);
  });

  it('should show loading indicator when isLoading is true', () => {
    render(<MessageList messages={mockChatMessages} isLoading={true} />);
    
    // Loading indicator shows animated dots (three divs with animate-bounce)
    const bounceElements = document.querySelectorAll('.animate-bounce');
    expect(bounceElements.length).toBe(3);
  });

  it('should not show loading indicator when isLoading is false', () => {
    render(<MessageList messages={mockChatMessages} isLoading={false} />);
    
    const bounceElements = document.querySelectorAll('.animate-bounce');
    expect(bounceElements.length).toBe(0);
  });

  it('renders GM message markdown as formatted content', () => {
    const messagesWithMarkdown = [
      {
        id: 'gm-1',
        project_id: 'proj-1',
        role: 'gm' as const,
        content: 'Here is **bold** and a list:\n- item one\n- item two',
        attachments: null,
        created_at: '2026-02-10T09:00:00Z',
      },
    ];
    render(<MessageList messages={messagesWithMarkdown} />);
    // Rendered markdown: "bold" appears inside <strong>, list items appear
    expect(screen.getByText('bold')).toBeInTheDocument();
    expect(screen.getByText('item one')).toBeInTheDocument();
    expect(screen.getByText('item two')).toBeInTheDocument();
    // Raw markdown asterisks should not appear as literal text in GM bubble
    const gmBubble = document.querySelector('.markdown-content');
    expect(gmBubble).toBeInTheDocument();
    expect(gmBubble?.textContent).toContain('bold');
  });

  it('renders user message as plain text (no markdown parsing)', () => {
    const messagesWithRawMarkdown = [
      {
        id: 'user-1',
        project_id: 'proj-1',
        role: 'user' as const,
        content: 'Please see **this** and `code`',
        attachments: null,
        created_at: '2026-02-10T09:00:00Z',
      },
    ];
    render(<MessageList messages={messagesWithRawMarkdown} />);
    // User message is shown as-is (plain text)
    expect(screen.getByText('Please see **this** and `code`')).toBeInTheDocument();
  });
});
