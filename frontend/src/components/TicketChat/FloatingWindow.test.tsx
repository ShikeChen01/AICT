import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingWindow } from './FloatingWindow';

describe('FloatingWindow', () => {
  it('renders nothing when isOpen is false', () => {
    render(
      <FloatingWindow title="Chat" isOpen={false} onClose={vi.fn()}>
        <div>Content</div>
      </FloatingWindow>
    );

    expect(screen.queryByText('Chat')).not.toBeInTheDocument();
    expect(screen.queryByText('Content')).not.toBeInTheDocument();
  });

  it('renders title and content when isOpen is true', () => {
    render(
      <FloatingWindow title="Engineer-1 — Need help" isOpen onClose={vi.fn()}>
        <div>Chat content</div>
      </FloatingWindow>
    );

    expect(screen.getByText('Engineer-1 — Need help')).toBeInTheDocument();
    expect(screen.getByText('Chat content')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <FloatingWindow title="Chat" isOpen onClose={onClose}>
        <div>Content</div>
      </FloatingWindow>
    );

    const closeButton = screen.getByRole('button', { name: /Close/i });
    fireEvent.click(closeButton);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
