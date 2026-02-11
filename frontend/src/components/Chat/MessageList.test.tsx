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
});
