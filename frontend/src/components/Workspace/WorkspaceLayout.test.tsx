/**
 * WorkspaceLayout — layout tests for the monitoring panel.
 *
 * Verifies that the aside element has proper height for the
 * monitoring panel (including VNC display) to render correctly.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Mock Sidebar and ConnectionStatus since they have their own deps
vi.mock('./Sidebar', () => ({
  Sidebar: () => <div data-testid="sidebar">Sidebar</div>,
}));
vi.mock('./ConnectionStatus', () => ({
  ConnectionStatus: () => <div data-testid="connection-status" />,
}));

import { WorkspaceLayout } from './WorkspaceLayout';

describe('WorkspaceLayout', () => {
  it('renders main content', () => {
    render(
      <WorkspaceLayout activeProjectId="proj-1" main={<div>Main content</div>} />
    );
    expect(screen.getByText('Main content')).toBeInTheDocument();
  });

  it('renders monitoring panel when provided', () => {
    render(
      <WorkspaceLayout
        activeProjectId="proj-1"
        main={<div>Main</div>}
        monitoringPanel={<div>Monitoring panel</div>}
      />
    );
    expect(screen.getByText('Monitoring panel')).toBeInTheDocument();
  });

  it('does not render aside when monitoring panel is undefined', () => {
    const { container } = render(
      <WorkspaceLayout activeProjectId="proj-1" main={<div>Main</div>} />
    );
    expect(container.querySelector('aside')).not.toBeInTheDocument();
  });

  it('aside has h-full class for explicit height propagation', () => {
    const { container } = render(
      <WorkspaceLayout
        activeProjectId="proj-1"
        main={<div>Main</div>}
        monitoringPanel={<div>Monitor</div>}
      />
    );
    const aside = container.querySelector('aside');
    expect(aside).toBeInTheDocument();
    expect(aside?.className).toContain('h-full');
  });

  it('aside has overflow-hidden to contain monitoring content', () => {
    const { container } = render(
      <WorkspaceLayout
        activeProjectId="proj-1"
        main={<div>Main</div>}
        monitoringPanel={<div>Monitor</div>}
      />
    );
    const aside = container.querySelector('aside');
    expect(aside?.className).toContain('overflow-hidden');
  });

  it('aside has fixed width from state', () => {
    const { container } = render(
      <WorkspaceLayout
        activeProjectId="proj-1"
        main={<div>Main</div>}
        monitoringPanel={<div>Monitor</div>}
      />
    );
    const aside = container.querySelector('aside');
    expect(aside?.style.width).toBe('384px');
  });

  it('renders resize separator between main and monitoring panel', () => {
    const { container } = render(
      <WorkspaceLayout
        activeProjectId="proj-1"
        main={<div>Main</div>}
        monitoringPanel={<div>Monitor</div>}
      />
    );
    const separator = container.querySelector('[role="separator"]');
    expect(separator).toBeInTheDocument();
    expect(separator?.getAttribute('aria-orientation')).toBe('vertical');
  });
});
