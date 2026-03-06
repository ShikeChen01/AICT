/**
 * Panel — layout tests.
 *
 * Verifies that the Panel body is a flex column container with overflow-hidden
 * so child components like VncView can properly fill the available space.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Panel } from './Panel';

describe('Panel', () => {
  it('renders title and subtitle', () => {
    render(<Panel title="Test Title" subtitle="Test subtitle">Content</Panel>);
    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByText('Test subtitle')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('renders header actions', () => {
    render(
      <Panel title="Panel" headerActions={<button>Action</button>}>
        Content
      </Panel>
    );
    expect(screen.getByText('Action')).toBeInTheDocument();
  });

  it('body is a flex column container for proper child layout', () => {
    const { container } = render(<Panel title="Test">Child</Panel>);
    const body = screen.getByText('Child').closest('div');
    expect(body?.className).toContain('flex');
    expect(body?.className).toContain('flex-col');
  });

  it('body has overflow-hidden to contain children', () => {
    render(<Panel title="Test">Child</Panel>);
    const body = screen.getByText('Child').closest('div');
    expect(body?.className).toContain('overflow-hidden');
  });

  it('body has min-h-0 and flex-1 for proper flex sizing', () => {
    render(<Panel title="Test">Child</Panel>);
    const body = screen.getByText('Child').closest('div');
    expect(body?.className).toContain('min-h-0');
    expect(body?.className).toContain('flex-1');
  });

  it('applies bodyClassName to body div', () => {
    render(<Panel title="Test" bodyClassName="custom-class">Child</Panel>);
    const body = screen.getByText('Child').closest('div');
    expect(body?.className).toContain('custom-class');
  });

  it('applies custom className to outer Card', () => {
    const { container } = render(<Panel className="custom-panel">Child</Panel>);
    const card = container.firstElementChild;
    expect(card?.className).toContain('custom-panel');
  });

  it('renders without header when no title/subtitle/actions', () => {
    const { container } = render(<Panel>Just content</Panel>);
    // Should not have a header with border-b
    const header = container.querySelector('.border-b');
    expect(header).not.toBeInTheDocument();
    expect(screen.getByText('Just content')).toBeInTheDocument();
  });
});
